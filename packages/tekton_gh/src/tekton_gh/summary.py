"""WP1d: the analysis summary - one page that says how a run went.

Lives here rather than in the component, so it can be tested without Rhino
and reused by the worker or a CI report. The component is a thin shell
around :func:`build_report`.

Three things it must get right, because each of them is a way to be quietly
wrong:

- **An equilibrium check.** The sum of the reactions against the sum of the
  applied loads catches a lost load or a wrong support faster than any
  amount of looking at colours.
- **Assumptions printed, not implied.** Every design number is accompanied
  by the k_mod, gamma_M and service class it used, and by the list of checks
  that were *not* run.
- **Absence stated.** No utilisation is "not computed", never 0.0.
"""

from __future__ import absolute_import

import math

#: Rows in the per-member CSV.
CSV_HEADER = (
    "member_id,load_case,position,material,section,"
    "governing_check,clause,ratio,stress_kN_m2,resistance_kN_m2,passes,notes"
)


def _vector_components(value):
    """(x, y, z) from a COMPAS Vector, a tuple, or None."""
    if value is None:
        return (0.0, 0.0, 0.0)
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, IndexError, KeyError):
        return (
            float(getattr(value, "x", 0.0)),
            float(getattr(value, "y", 0.0)),
            float(getattr(value, "z", 0.0)),
        )


def _magnitude(value):
    x, y, z = _vector_components(value)
    return math.sqrt(x * x + y * y + z * z)


def deformation_summary(result_set):
    """Max and mean displacement, and where the maximum sits.

    Plate samples count too. In a pure plate model the only `node_results`
    are the outline nodes, which carry the supports and therefore do not
    move - reporting their maximum would say "0 m" about a plate that is
    visibly sagging. The interesting displacement lives on the mesh, in
    `surface_results`.
    """
    magnitudes = [
        (node.node_id, _magnitude(node.displacement))
        for node in (getattr(result_set, "node_results", None) or {}).values()
    ]
    for surface_id, samples in (getattr(result_set, "surface_results", None) or {}).items():
        for sample in samples or []:
            label = (sample.metadata or {}).get("node_tag", "surface {}".format(surface_id))
            magnitudes.append((label, _magnitude(sample.displacement)))
    if not magnitudes:
        return None
    worst_node, worst = max(magnitudes, key=lambda item: item[1])
    total = sum(value for _, value in magnitudes)
    return {
        "max": worst,
        "max_node": worst_node,
        "mean": total / len(magnitudes),
        "count": len(magnitudes),
    }


def reaction_summary(result_set):
    """Sum of the support reactions, per direction."""
    nodes = [
        node
        for node in (getattr(result_set, "node_results", None) or {}).values()
        if getattr(node, "reaction_force", None) is not None
    ]
    if not nodes:
        return None
    totals = [0.0, 0.0, 0.0]
    for node in nodes:
        x, y, z = _vector_components(node.reaction_force)
        totals[0] += x
        totals[1] += y
        totals[2] += z
    return {"fx": totals[0], "fy": totals[1], "fz": totals[2], "count": len(nodes)}


def applied_load_total(model, load_case_id):
    """Sum of the authored point loads for a load case, per direction.

    Member loads and self-weight are deliberately not integrated here: doing
    it properly needs the member lengths and the section volumes, and a
    half-correct total would make the equilibrium check lie. When point
    loads are all there is, the check is exact; otherwise the report says
    the comparison is partial.
    """
    totals = [0.0, 0.0, 0.0]
    count = 0
    for load in getattr(model, "point_loads", []) or []:
        if getattr(load, "load_case_id", None) != load_case_id:
            continue
        x, y, z = _vector_components(getattr(load, "force", None))
        totals[0] += x
        totals[1] += y
        totals[2] += z
        count += 1

    # Plate pressures integrate exactly over the plate area, so unlike member
    # loads they can be summed here without needing the mesh.
    areas = _surface_areas(model)
    for load in getattr(model, "surface_loads", []) or []:
        if getattr(load, "load_case_id", None) != load_case_id:
            continue
        area = areas.get(getattr(load, "surface_id", None))
        if area is None:
            continue
        x, y, z = _vector_components(getattr(load, "pressure", None))
        totals[0] += x * area
        totals[1] += y * area
        totals[2] += z * area
        count += 1
    has_other = any(
        getattr(load, "load_case_id", None) == load_case_id
        for load in (getattr(model, "member_loads", []) or [])
    )
    case = next(
        (c for c in getattr(model, "load_cases", []) or [] if getattr(c, "id", None) == load_case_id),
        None,
    )
    self_weight = bool(getattr(case, "self_weight", False))
    if self_weight:
        # A plate's own weight is thickness x density x area - exact, so it
        # can be summed. A beam's needs its length and section, which is the
        # part that stays out of this sum.
        thicknesses = {t.id: t for t in getattr(model, "thicknesses", []) or []}
        materials = getattr(model, "materials", {}) or {}
        for surface in getattr(model, "surfaces", []) or []:
            thickness = thicknesses.get(getattr(surface, "thickness_id", None))
            area = areas.get(surface.id)
            if thickness is None or area is None:
                continue
            material = materials.get(getattr(thickness, "material_id", None))
            density = getattr(material, "density_mean", 0.0) or 0.0
            totals[2] -= density * 9.81 / 1000.0 * float(thickness.thickness) * area
            count += 1
        self_weight = bool(getattr(model, "members", None))       # beams still unaccounted
    return {
        "fx": totals[0],
        "fy": totals[1],
        "fz": totals[2],
        "count": count,
        "partial": has_other or self_weight,
    }


def _surface_areas(model):
    """Plan area of every plate, from its outline polygon.

    Computed here rather than taken from a mesh: the equilibrium check must
    work for any backend, including one whose mesh we never see.
    """
    points = {node.id: node.point for node in getattr(model, "nodes", []) or []}
    areas = {}
    for surface in getattr(model, "surfaces", []) or []:
        corners = [points[i] for i in surface.nodes if i in points]
        if len(corners) < 3:
            continue
        # Newell's method: the polygon's area vector, valid for any plane.
        nx = ny = nz = 0.0
        for current, following in zip(corners, corners[1:] + corners[:1]):
            nx += current[1] * following[2] - current[2] * following[1]
            ny += current[2] * following[0] - current[0] * following[2]
            nz += current[0] * following[1] - current[1] * following[0]
        areas[surface.id] = 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    return areas


def force_extremes(result_set):
    """Extreme section forces over all member samples."""
    quantities = ("axial", "shear_y", "shear_z", "torsion", "moment_y", "moment_z")
    extremes = {}
    for member_id, samples in (getattr(result_set, "member_results", None) or {}).items():
        for sample in samples or []:
            for quantity in quantities:
                value = float(getattr(sample, quantity, 0.0) or 0.0)
                current = extremes.get(quantity)
                if current is None or abs(value) > abs(current["value"]):
                    extremes[quantity] = {
                        "value": value,
                        "member_id": member_id,
                        "position": getattr(sample, "position", 0.0),
                    }
    return extremes


def _format_number(value, digits=3):
    if value is None:
        return "n/a"
    if value == 0:
        return "0"
    if abs(value) < 0.001 or abs(value) >= 100000:
        return "{:.{d}e}".format(value, d=digits)
    return "{:.{d}f}".format(value, d=digits)


def build_report(model, checks_by_case=None, assumptions=None, title="Tekton analysis summary", worst_count=10):
    """Build the text report.

    Parameters
    ----------
    model : StructuralModel
        With ``results`` filled.
    checks_by_case : dict, optional
        ``{load_case_id: [MemberCheck, ...]}`` from
        :func:`compas_timber_fea.design.check_model`. When absent, the
        utilisation section says it was not computed.
    assumptions : DesignAssumptions, optional
        Printed verbatim when design checks were run.
    worst_count : int
        How many of the worst members to list per load case.

    Returns
    -------
    str
    """
    lines = [title, "=" * len(title), ""]

    members = getattr(model, "members", []) or []
    beams = [m for m in members if getattr(m, "member_type", "BEAM") == "BEAM"]
    lines.append("Model")
    lines.append("-----")
    lines.append("  Nodes         {}".format(len(getattr(model, "nodes", []) or [])))
    lines.append("  Members       {} ({} beams)".format(len(members), len(beams)))
    lines.append("  Surfaces      {}".format(len(getattr(model, "surfaces", []) or [])))
    lines.append("  Supports      {}".format(len(getattr(model, "supports", []) or [])))
    lines.append("  Load cases    {}".format(len(getattr(model, "load_cases", []) or [])))
    lines.append("")

    results = getattr(model, "results", {}) or {}
    if not results:
        lines.append("No results on this model - nothing was calculated yet.")
        return "\n".join(lines)

    case_names = {
        getattr(case, "id", None): getattr(case, "name", "")
        for case in getattr(model, "load_cases", []) or []
    }

    for case_id, result_set in sorted(results.items()):
        name = case_names.get(case_id) or getattr(result_set, "name", "") or "case {}".format(case_id)
        metadata = getattr(result_set, "metadata", None) or {}
        # A combination is assembled, not solved. Saying so matters: the
        # factors are what an engineer checks first, and superposition is
        # only valid while the model is linear.
        if metadata.get("source") == "superposition":
            heading = "Combination {} - {}".format(case_id, name)
            terms = ", ".join(
                "{}x LC{}".format(_format_number(factor, 2), key)
                for key, factor in sorted(metadata.get("factors", {}).items())
            )
            lines.append(heading)
            lines.append("-" * len(heading))
            if terms:
                lines.append("  from        {}".format(terms))
            lines.append("  assembled by superposition (valid for a linear model)")
        else:
            heading = "Load case {} - {}".format(case_id, name)
            lines.append(heading)
            lines.append("-" * len(heading))

        deformation = deformation_summary(result_set)
        if deformation:
            lines.append("  Displacement")
            lines.append(
                "    max        {} m  at node {}".format(
                    _format_number(deformation["max"], 4), deformation["max_node"]
                )
            )
            lines.append("    mean       {} m  over {} nodes".format(
                _format_number(deformation["mean"], 4), deformation["count"]
            ))
        else:
            lines.append("  Displacement  no nodal results")

        reactions = reaction_summary(result_set)
        if reactions:
            applied = applied_load_total(model, case_id)
            lines.append("  Reactions ({} supported nodes)".format(reactions["count"]))
            lines.append(
                "    sum        Fx {}  Fy {}  Fz {}  kN".format(
                    _format_number(reactions["fx"]),
                    _format_number(reactions["fy"]),
                    _format_number(reactions["fz"]),
                )
            )
            if applied["count"] or applied["partial"]:
                lines.append(
                    "    applied    Fx {}  Fy {}  Fz {}  kN{}".format(
                        _format_number(applied["fx"]),
                        _format_number(applied["fy"]),
                        _format_number(applied["fz"]),
                        " (point loads only)" if applied["partial"] else "",
                    )
                )
                if not applied["partial"]:
                    residual = math.sqrt(
                        (reactions["fx"] + applied["fx"]) ** 2
                        + (reactions["fy"] + applied["fy"]) ** 2
                        + (reactions["fz"] + applied["fz"]) ** 2
                    )
                    reference = max(1e-9, _magnitude((applied["fx"], applied["fy"], applied["fz"])))
                    verdict = "OK" if residual / reference < 0.01 else "CHECK THE MODEL"
                    lines.append(
                        "    equilibrium  residual {} kN  ({:.2%} of applied) - {}".format(
                            _format_number(residual), residual / reference, verdict
                        )
                    )
                else:
                    lines.append(
                        "    equilibrium  not checked - member loads or self-weight are not summed here"
                    )

        extremes = force_extremes(result_set)
        if extremes:
            lines.append("  Section forces (extremes)")
            labels = (
                ("axial", "N   ", "kN"),
                ("shear_y", "Vy  ", "kN"),
                ("shear_z", "Vz  ", "kN"),
                ("torsion", "Mt  ", "kNm"),
                ("moment_y", "My  ", "kNm"),
                ("moment_z", "Mz  ", "kNm"),
            )
            for key, label, unit in labels:
                entry = extremes.get(key)
                if entry is None:
                    continue
                lines.append(
                    "    {} {:>12} {}  at member {} (t={:.2f})".format(
                        label, _format_number(entry["value"]), unit, entry["member_id"], entry["position"]
                    )
                )

        case_checks = (checks_by_case or {}).get(case_id)
        if case_checks is None:
            lines.append("  Utilisation   not computed")
        elif not case_checks:
            lines.append("  Utilisation   no member could be checked (see notes)")
        else:
            from compas_timber_fea.design.checks import worst_per_member

            worst = worst_per_member(case_checks)
            failing = [entry for entry in worst if not entry.passes]
            lines.append("  Utilisation")
            lines.append(
                "    max        {:.3f}  member {} ({}, {})".format(
                    worst[0].ratio,
                    worst[0].member_id,
                    worst[0].governing.name if worst[0].governing else "-",
                    worst[0].governing.clause if worst[0].governing else "-",
                )
            )
            mean = sum(entry.ratio for entry in worst) / len(worst)
            lines.append("    mean       {:.3f}  over {} members".format(mean, len(worst)))
            lines.append("    above 1.0  {}".format(len(failing)))
            lines.append("    worst members")
            for entry in worst[:worst_count]:
                lines.append(
                    "      {:>6}  {:.3f}  {:<22} {:<7} t={:.2f}  {}".format(
                        entry.member_id,
                        entry.ratio,
                        entry.governing.name if entry.governing else "-",
                        entry.governing.clause if entry.governing else "-",
                        entry.position,
                        "" if entry.passes else "EXCEEDED",
                    )
                )
        lines.append("")

    if assumptions is not None and checks_by_case:
        lines.append("Design assumptions")
        lines.append("------------------")
        for line in assumptions.describe():
            lines.append("  " + line)
        lines.append("")
        lines.append("  These are assumptions, not results. Stability was not verified;")
        lines.append("  a member that passes here may still fail on buckling.")
        lines.append("")
        lines.append("  NOT VERIFIED BY AN ENGINEER: the code tables behind these numbers")
        lines.append("  (k_mod, gamma_M, material strengths, psi factors) were transcribed")
        lines.append("  from the Eurocodes by a developer and carry the base recommended")
        lines.append("  values, not a national annex. Use for orientation during design,")
        lines.append("  not for verification.")
        lines.append("")

    return "\n".join(lines)


def build_csv(checks_by_case):
    """One row per member sample, worst-first within each load case."""
    rows = [CSV_HEADER]
    for case_id, checks in sorted((checks_by_case or {}).items()):
        for entry in checks:
            governing = entry.governing
            rows.append(
                "{},{},{:.3f},{},{},{},{},{:.4f},{:.1f},{:.1f},{},{}".format(
                    entry.member_id,
                    case_id,
                    entry.position,
                    _csv_escape(entry.material_name),
                    _csv_escape(entry.section_name),
                    _csv_escape(governing.name if governing else ""),
                    _csv_escape(governing.clause if governing else ""),
                    entry.ratio,
                    governing.stress if governing else 0.0,
                    governing.resistance if governing else 0.0,
                    "yes" if entry.passes else "NO",
                    _csv_escape("; ".join(entry.notes)),
                )
            )
    return "\n".join(rows)


def _csv_escape(value):
    text = str(value or "")
    if "," in text or '"' in text:
        return '"{}"'.format(text.replace('"', '""'))
    return text


def headline_numbers(model, checks_by_case=None):
    """The few values worth having as separate outputs."""
    out = {
        "max_displacement": 0.0,
        "max_displacement_node": None,
        "max_utilization": None,
        "max_utilization_member": None,
        "members_over_1": 0,
        "governing_check": "",
    }
    for result_set in (getattr(model, "results", {}) or {}).values():
        deformation = deformation_summary(result_set)
        if deformation and deformation["max"] > out["max_displacement"]:
            out["max_displacement"] = deformation["max"]
            out["max_displacement_node"] = deformation["max_node"]
    if checks_by_case:
        from compas_timber_fea.design.checks import worst_per_member

        everything = [entry for checks in checks_by_case.values() for entry in checks]
        if everything:
            worst = worst_per_member(everything)
            out["max_utilization"] = worst[0].ratio
            out["max_utilization_member"] = worst[0].member_id
            out["members_over_1"] = len([entry for entry in worst if not entry.passes])
            out["governing_check"] = worst[0].governing.name if worst[0].governing else ""
    return out
