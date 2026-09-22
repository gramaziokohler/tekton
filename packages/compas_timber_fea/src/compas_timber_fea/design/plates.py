"""EC5 checks for plates, from the shell results.

.. warning::

   **Not checked by a structural engineer** - the same caveat as the member
   checks, see the warning section in ``docs/discussion/work-packages.md``.
   For plates it bites harder, because of the scope limit below.

What a shell gives us is forces *per metre of width*: bending moments
``m_x``, ``m_y``, the twisting moment ``m_xy``, and membrane forces ``n_x``,
``n_y``, ``n_xy``. Turning those into a utilisation needs a section, and for
a plate the section is one metre wide by the plate's thickness.

**The scope limit, stated up front.** These checks treat the plate as a
homogeneous isotropic slab. That is right for a solid timber deck and wrong
for CLT, whose layers alternate direction: a real CLT check uses the net
cross-section of the layers running in the direction considered, which is a
fraction of the gross one, and the resistance differs between the two
directions. Tekton carries no layup today (WP7's open half), and
``StructuralThickness`` names one material and one thickness. So:

- For a solid or homogeneous plate these numbers are meaningful.
- For CLT they are **unconservative in the weak direction** and roughly
  right in the strong one, and every result carries a note saying so.

The honest fix is a layup on the material (EN 16351) plus net-section
properties per direction. Until then this is a screening check, and the
report says which.

Clause numbers are EN 1995-1-1.
"""

from dataclasses import dataclass
from dataclasses import field

from ..core.materials import Material
from .checks import MPA_TO_KN_M2
from .checks import CheckResult
from .factors import DesignAssumptions
from .factors import k_h_bending

#: A plate's results are per metre of width, so the section that carries
#: them is one metre wide.
UNIT_WIDTH = 1.0


@dataclass
class PlateCheck:
    """All checks for one plate at one sample, plus what governed."""

    surface_id: int
    load_case_id: int
    position: object = None
    checks: list = field(default_factory=list)
    material_name: str = ""
    thickness: float = 0.0
    k_mod: float = 0.0
    gamma_M: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def governing(self):
        return max(self.checks, key=lambda check: check.ratio) if self.checks else None

    @property
    def ratio(self):
        governing = self.governing
        return governing.ratio if governing else 0.0

    @property
    def passes(self):
        return self.ratio <= 1.0


def plate_section_properties(thickness):
    """Area and section modulus of a one-metre strip.

    A = 1.0 * t (m2/m), W = 1.0 * t^2 / 6 (m3/m) - the same rectangle as a
    beam, only the width is fixed at a metre because that is the width the
    shell results are given for.
    """
    thickness = float(thickness)
    if thickness <= 0:
        raise ValueError("Plate thickness must be positive, got {}.".format(thickness))
    return {
        "area": UNIT_WIDTH * thickness,
        "modulus": UNIT_WIDTH * thickness ** 2 / 6.0,
    }


def _design_strength(f_k, k_mod_value, gamma_M, k_h=1.0):
    if not f_k or f_k <= 0:
        return 0.0
    return k_mod_value * k_h * f_k * MPA_TO_KN_M2 / gamma_M


def _ratio(stress, resistance):
    if resistance <= 0:
        return 0.0
    return abs(stress) / resistance


def check_plate_sample(model, surface, sample, assumptions=None, load_case=None):
    """Run the plate checks for one sample of one plate.

    Parameters
    ----------
    model : StructuralModel
    surface : StructuralSurface
    sample : StructuralSurfaceResult
        One point on the plate, carrying m_x, m_y, n_x, n_y.
    assumptions : DesignAssumptions, optional
    load_case : StructuralLoadCase, optional

    Returns
    -------
    PlateCheck
    """
    assumptions = assumptions or DesignAssumptions()
    check = PlateCheck(
        surface_id=getattr(surface, "id", getattr(sample, "surface_id", -1)),
        load_case_id=getattr(sample, "load_case_id", 0),
        position=getattr(sample, "position", None),
    )

    thicknesses = {t.id: t for t in getattr(model, "thicknesses", []) or []}
    entry = thicknesses.get(getattr(surface, "thickness_id", None))
    if entry is None:
        check.notes.append("no thickness - not checked")
        return check

    try:
        properties = plate_section_properties(entry.thickness)
    except ValueError as error:
        check.notes.append(str(error))
        return check

    material = Material.resolve((getattr(model, "materials", {}) or {}).get(
        getattr(entry, "material_id", None)))
    check.material_name = material.name
    check.thickness = float(entry.thickness)
    if material.is_assumed:
        check.notes.append("material properties assumed ({})".format(material.standard))

    # The layup caveat, on every plate: it decides whether the number can be
    # trusted, so it must not live only in a docstring.
    check.notes.append(
        "homogeneous isotropic slab assumed - for CLT this is unconservative "
        "across the layers (no layup in the model yet)")
    if getattr(surface, "span_direction", None) is not None:
        check.notes.append("span_direction is set but not used by this check")

    k_mod_value = assumptions.k_mod_for(load_case)
    gamma_M = assumptions.gamma_M_value(material)
    check.k_mod = k_mod_value
    check.gamma_M = gamma_M
    k_h = k_h_bending(material, entry.thickness) if assumptions.size_factor else 1.0

    area = properties["area"]
    modulus = properties["modulus"]

    m_x = float(getattr(sample, "moment_x", 0.0) or 0.0)
    m_y = float(getattr(sample, "moment_y", 0.0) or 0.0)
    n_x = float(getattr(sample, "membrane_force_x", 0.0) or 0.0)
    n_y = float(getattr(sample, "membrane_force_y", 0.0) or 0.0)

    f_md = _design_strength(material.f_mk, k_mod_value, gamma_M, k_h)

    # --- bending, 6.1.6, in each direction separately -------------------
    # Not the biaxial k_m interaction of a beam: the two directions of a
    # plate are separate strips, not two axes of one cross-section.
    for label, moment in (("x", m_x), ("y", m_y)):
        if f_md > 0 and moment:
            sigma = moment / modulus
            check.checks.append(CheckResult(
                name="bending {}".format(label),
                clause="6.1.6",
                ratio=_ratio(sigma, f_md),
                stress=abs(sigma),
                resistance=f_md,
                detail="per metre width, k_h={:.3f}".format(k_h),
            ))

    # --- membrane, 6.1.2 / 6.1.4 ----------------------------------------
    for label, force in (("x", n_x), ("y", n_y)):
        if not force or not area:
            continue
        sigma = force / area
        if force > 0:
            f_d = _design_strength(material.f_t0k, k_mod_value, gamma_M)
            name, clause = "tension {}".format(label), "6.1.2"
        else:
            f_d = _design_strength(material.f_c0k, k_mod_value, gamma_M)
            name, clause = "compression {}".format(label), "6.1.4"
        if f_d > 0:
            check.checks.append(CheckResult(
                name=name, clause=clause,
                ratio=_ratio(sigma, f_d), stress=abs(sigma), resistance=f_d,
                detail="per metre width",
            ))

    # --- combined bending + membrane, 6.2.3 / 6.2.4 ---------------------
    for label, moment, force in (("x", m_x, n_x), ("y", m_y, n_y)):
        if not (f_md > 0 and moment and force and area):
            continue
        bending_ratio = _ratio(moment / modulus, f_md)
        sigma_n = force / area
        if force > 0:
            f_d = _design_strength(material.f_t0k, k_mod_value, gamma_M)
            if f_d > 0:
                check.checks.append(CheckResult(
                    name="bending + tension {}".format(label), clause="6.2.3",
                    ratio=_ratio(sigma_n, f_d) + bending_ratio,
                    stress=abs(sigma_n), resistance=f_d, detail="linear interaction"))
        else:
            f_d = _design_strength(material.f_c0k, k_mod_value, gamma_M)
            if f_d > 0:
                check.checks.append(CheckResult(
                    name="bending + compression {}".format(label), clause="6.2.4",
                    ratio=_ratio(sigma_n, f_d) ** 2 + bending_ratio,
                    stress=abs(sigma_n), resistance=f_d,
                    detail="axial term squared; plate buckling not verified"))

    if not check.checks:
        check.notes.append("no check applicable (no forces, or no strength values)")
    return check


def check_plates(model, assumptions=None, load_case_ids=None):
    """Run the plate checks over every surface sample in the model's results.

    Returns
    -------
    dict
        ``{load_case_id: [PlateCheck, ...]}``, worst first.
    """
    assumptions = assumptions or DesignAssumptions()
    surfaces = {s.id: s for s in getattr(model, "surfaces", []) or []}
    load_cases = {c.id: c for c in getattr(model, "load_cases", []) or []}

    out = {}
    for case_id, result_set in sorted((getattr(model, "results", {}) or {}).items()):
        if load_case_ids is not None and case_id not in load_case_ids:
            continue
        load_case = load_cases.get(case_id)
        checks = []
        for surface_id, samples in sorted((getattr(result_set, "surface_results", None) or {}).items()):
            surface = surfaces.get(surface_id)
            if surface is None:
                continue
            for sample in samples or []:
                checks.append(check_plate_sample(model, surface, sample, assumptions, load_case))
        if checks:
            checks.sort(key=lambda check: check.ratio, reverse=True)
            out[case_id] = checks
    return out


def worst_per_plate(checks):
    """Collapse per-sample checks to one worst entry per plate."""
    worst = {}
    for check in checks:
        current = worst.get(check.surface_id)
        if current is None or check.ratio > current.ratio:
            worst[check.surface_id] = check
    return sorted(worst.values(), key=lambda check: check.ratio, reverse=True)
