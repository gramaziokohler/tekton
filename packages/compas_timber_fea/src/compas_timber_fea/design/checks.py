"""The EC5 checks that need no stability assumption.

Implemented here (WP1b): bending about both axes with the k_m interaction,
tension and compression parallel to grain, shear, and the bending+axial
interactions of 6.2.3 and 6.2.4.

Deliberately absent: buckling (6.3.2) and lateral-torsional buckling
(6.3.3). Both need a buckling length, which the neutral model does not
carry - see WP1c. :class:`DesignAssumptions` lists them under
``not_verified`` so every report says so out loud.

Unit bridge: the result model carries forces in kN and kNm and lengths in
metres, so a stress comes out in kN/m2. Material strengths are in MPa
(= N/mm2 = 1000 kN/m2). :data:`MPA_TO_KN_M2` is the only place that factor
appears; getting it wrong by 1000 is the failure mode this module has to
make impossible.
"""

from dataclasses import dataclass
from dataclasses import field

from ..core.materials import Material
from .factors import K_M_OTHER
from .factors import K_M_RECTANGULAR
from .factors import DesignAssumptions
from .factors import k_h_bending
from .sections import section_properties

#: 1 MPa = 1 N/mm2 = 1000 kN/m2.
MPA_TO_KN_M2 = 1000.0


@dataclass
class CheckResult:
    """One verified criterion at one location."""

    name: str
    clause: str
    ratio: float
    stress: float = 0.0          # kN/m2
    resistance: float = 0.0      # kN/m2
    detail: str = ""

    @property
    def passes(self):
        return self.ratio <= 1.0


@dataclass
class MemberCheck:
    """All checks for one member in one load case, plus what governed."""

    member_id: int
    load_case_id: int
    position: float = 0.0
    checks: list = field(default_factory=list)
    material_name: str = ""
    section_name: str = ""
    k_mod: float = 0.0
    gamma_M: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def governing(self):
        """The check with the highest ratio, or None when nothing ran."""
        return max(self.checks, key=lambda check: check.ratio) if self.checks else None

    @property
    def ratio(self):
        governing = self.governing
        return governing.ratio if governing else 0.0

    @property
    def passes(self):
        return self.ratio <= 1.0


def _design_strength(f_k, k_mod_value, gamma_M, k_h=1.0):
    """f_d = k_mod * k_h * f_k / gamma_M, converted to kN/m2."""
    if not f_k or f_k <= 0:
        return 0.0
    return k_mod_value * k_h * f_k * MPA_TO_KN_M2 / gamma_M


def _ratio(stress, resistance):
    """Utilisation, guarding a zero resistance.

    A missing strength value yields 0.0 rather than infinity, and the caller
    notes that the check could not be run - an unrunnable check must not
    masquerade as a failed one, nor as a passed one.
    """
    if resistance <= 0:
        return 0.0
    return abs(stress) / resistance


def check_member(model, member, result, assumptions=None, load_case=None):
    """Run the WP1b checks for one member at one result location.

    Parameters
    ----------
    model : StructuralModel
    member : StructuralMember
    result : StructuralMemberResult
        One sample along the member, carrying the section forces.
    assumptions : DesignAssumptions, optional
    load_case : StructuralLoadCase, optional
        Used to infer the duration class when none is set explicitly.

    Returns
    -------
    MemberCheck
    """
    assumptions = assumptions or DesignAssumptions()
    check = MemberCheck(
        member_id=getattr(member, "id", getattr(result, "member_id", -1)),
        load_case_id=getattr(result, "load_case_id", 0),
        position=getattr(result, "position", 0.0),
    )

    sections = {section.id: section for section in getattr(model, "sections", [])}
    section = sections.get(getattr(member, "section_id", None))
    if section is None:
        check.notes.append("no section - not checked")
        return check

    try:
        properties = section_properties(section)
    except ValueError as error:
        check.notes.append(str(error))
        return check

    material = Material.resolve(getattr(model, "materials", {}).get(getattr(section, "material_id", None)))
    check.material_name = material.name
    check.section_name = getattr(section, "name", "") or ""
    if material.is_assumed:
        check.notes.append("material properties assumed ({})".format(material.standard))
    if properties["is_approximated"]:
        check.notes.append("section shape {!r} approximated as rectangular".format(properties["shape"]))

    k_mod_value = assumptions.k_mod_for(load_case)
    gamma_M = assumptions.gamma_M_value(material)
    check.k_mod = k_mod_value
    check.gamma_M = gamma_M

    height = float(getattr(section, "height", 0.0) or 0.0)
    k_h = k_h_bending(material, height)

    area = properties["area"]
    W_y = properties["W_y"]
    W_z = properties["W_z"]

    axial = float(getattr(result, "axial", 0.0) or 0.0)
    moment_y = float(getattr(result, "moment_y", 0.0) or 0.0)
    moment_z = float(getattr(result, "moment_z", 0.0) or 0.0)
    shear_y = float(getattr(result, "shear_y", 0.0) or 0.0)
    shear_z = float(getattr(result, "shear_z", 0.0) or 0.0)

    # --- bending, 6.1.6 -------------------------------------------------
    f_md = _design_strength(material.f_mk, k_mod_value, gamma_M, k_h)
    sigma_my = moment_y / W_y if W_y else 0.0
    sigma_mz = moment_z / W_z if W_z else 0.0
    k_m = K_M_RECTANGULAR if properties["shape"] == "rectangular" else K_M_OTHER

    if f_md > 0 and (sigma_my or sigma_mz):
        # 6.1.6: both permutations, the governing one is the larger.
        ratio_1 = _ratio(sigma_my, f_md) + k_m * _ratio(sigma_mz, f_md)
        ratio_2 = k_m * _ratio(sigma_my, f_md) + _ratio(sigma_mz, f_md)
        check.checks.append(
            CheckResult(
                name="bending",
                clause="6.1.6",
                ratio=max(ratio_1, ratio_2),
                stress=max(abs(sigma_my), abs(sigma_mz)),
                resistance=f_md,
                detail="k_m={:.1f}, k_h={:.3f}".format(k_m, k_h),
            )
        )

    # --- axial, 6.1.2 / 6.1.4 -------------------------------------------
    sigma_axial = axial / area if area else 0.0
    if axial > 0:
        f_t0d = _design_strength(material.f_t0k, k_mod_value, gamma_M)
        if f_t0d > 0:
            check.checks.append(
                CheckResult(
                    name="tension parallel",
                    clause="6.1.2",
                    ratio=_ratio(sigma_axial, f_t0d),
                    stress=abs(sigma_axial),
                    resistance=f_t0d,
                )
            )
    elif axial < 0:
        f_c0d = _design_strength(material.f_c0k, k_mod_value, gamma_M)
        if f_c0d > 0:
            check.checks.append(
                CheckResult(
                    name="compression parallel",
                    clause="6.1.4",
                    ratio=_ratio(sigma_axial, f_c0d),
                    stress=abs(sigma_axial),
                    resistance=f_c0d,
                    detail="cross-section only, no buckling",
                )
            )

    # --- shear, 6.1.7 ---------------------------------------------------
    f_vd = _design_strength(material.f_vk, k_mod_value, gamma_M)
    shear = max(abs(shear_y), abs(shear_z))
    if f_vd > 0 and shear and area:
        tau = properties["shear_factor"] * shear / area
        check.checks.append(
            CheckResult(
                name="shear",
                clause="6.1.7",
                ratio=_ratio(tau, f_vd),
                stress=tau,
                resistance=f_vd,
                detail="factor {:.2f}".format(properties["shear_factor"]),
            )
        )

    # --- combined, 6.2.3 / 6.2.4 ----------------------------------------
    if f_md > 0 and (sigma_my or sigma_mz):
        bending_term = max(
            _ratio(sigma_my, f_md) + k_m * _ratio(sigma_mz, f_md),
            k_m * _ratio(sigma_my, f_md) + _ratio(sigma_mz, f_md),
        )
        if axial > 0:
            f_t0d = _design_strength(material.f_t0k, k_mod_value, gamma_M)
            if f_t0d > 0:
                check.checks.append(
                    CheckResult(
                        name="bending + tension",
                        clause="6.2.3",
                        ratio=_ratio(sigma_axial, f_t0d) + bending_term,
                        stress=abs(sigma_axial),
                        resistance=f_t0d,
                        detail="linear interaction",
                    )
                )
        elif axial < 0:
            f_c0d = _design_strength(material.f_c0k, k_mod_value, gamma_M)
            if f_c0d > 0:
                check.checks.append(
                    CheckResult(
                        name="bending + compression",
                        clause="6.2.4",
                        ratio=_ratio(sigma_axial, f_c0d) ** 2 + bending_term,
                        stress=abs(sigma_axial),
                        resistance=f_c0d,
                        detail="axial term squared; stability not verified",
                    )
                )

    if not check.checks:
        check.notes.append("no check applicable (no forces, or no strength values)")

    return check


def check_model(model, assumptions=None, load_case_ids=None):
    """Run the checks over every member sample in the model's results.

    Returns
    -------
    dict
        ``{load_case_id: [MemberCheck, ...]}``, one entry per member sample
        that could be checked, worst-first within each load case.
    """
    assumptions = assumptions or DesignAssumptions()
    members = {member.id: member for member in getattr(model, "members", [])}
    load_cases = {case.id: case for case in getattr(model, "load_cases", [])}

    out = {}
    for case_id, result_set in sorted(getattr(model, "results", {}).items()):
        if load_case_ids is not None and case_id not in load_case_ids:
            continue
        load_case = load_cases.get(case_id)
        checks = []
        for member_id, samples in sorted((result_set.member_results or {}).items()):
            member = members.get(member_id)
            if member is None:
                continue
            if getattr(member, "member_type", "BEAM") != "BEAM":
                # Rigid links and couplings carry no timber section.
                continue
            for sample in samples or []:
                checks.append(check_member(model, member, sample, assumptions, load_case))
        checks.sort(key=lambda check: check.ratio, reverse=True)
        out[case_id] = checks
    return out


def worst_per_member(checks):
    """Collapse per-sample checks to one worst entry per member."""
    worst = {}
    for check in checks:
        current = worst.get(check.member_id)
        if current is None or check.ratio > current.ratio:
            worst[check.member_id] = check
    return sorted(worst.values(), key=lambda check: check.ratio, reverse=True)
