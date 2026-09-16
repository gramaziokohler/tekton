"""The per-load-case loop: loads in, solve, read, clean up.

One ``pattern Plain`` per neutral load case; after reading, the pattern is
removed and the analysis state reset, so the cases come out independent
(proven in the spike). Self-weight is a member load of ρ·A·g per beam,
projected onto the member's local axes - OpenSees has no automatic
self-weight for beams.

``analyze()`` never raises: a non-zero return is the only failure signal,
and OpenSees prints its complaints to stdout in C++. The loop turns a
non-zero return into an exception naming the load case, because a silent
"0 results" is the failure mode this backend is most prone to.
"""

from compas_opensees.builder import member_uniform_load


class AnalysisError(RuntimeError):
    """OpenSees could not solve a load case."""


def _static_linear(ops):
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Transformation")
    ops.integrator("LoadControl", 1)
    ops.algorithm("Linear")
    ops.analysis("Static")


def apply_case(ops, model, built, case, time_series_tag=1):
    """Emit the loads of one load case into a fresh pattern; returns the pattern tag."""
    tag = int(case.id)
    ops.pattern("Plain", tag, time_series_tag)

    for load in model.point_loads:
        if load.load_case_id != case.id or load.node_id not in built.node_tags:
            continue
        f = load.force
        m = load.moment if load.moment is not None else (0.0, 0.0, 0.0)
        ops.load(int(load.node_id), float(f[0]), float(f[1]), float(f[2]), float(m[0]), float(m[1]), float(m[2]))

    for load in model.member_loads:
        if load.load_case_id != case.id or load.member_id not in built.member_elements:
            continue
        wy, wz, wx = member_uniform_load(built, load.member_id, load.force)
        a, b = float(load.dist_start or 0.0), float(load.dist_end if load.dist_end is not None else 1.0)
        if a <= 0.0 and b >= 1.0:
            ops.eleLoad("-ele", built.member_elements[load.member_id], "-type", "-beamUniform", wy, wz, wx)
        else:
            # partial uniform: -beamUniform Wy Wz Wx aOverL bOverL Wyb Wzb Wxb
            ops.eleLoad("-ele", built.member_elements[load.member_id], "-type", "-beamUniform", wy, wz, wx, a, b, wy, wz, wx)

    if getattr(case, "self_weight", False):
        for member_id, w in built.member_self_weight.items():
            if w <= 0.0 or built.member_kind.get(member_id) != "beam":
                continue
            wy, wz, wx = member_uniform_load(built, member_id, (0.0, 0.0, -w))
            ops.eleLoad("-ele", built.member_elements[member_id], "-type", "-beamUniform", wy, wz, wx)
    return tag


def solve_case(ops, case_tag, case_name=""):
    _static_linear(ops)
    status = ops.analyze(1)
    if status != 0:
        raise AnalysisError(
            "OpenSees failed to solve load case {}{} (analyze returned {}). A singular system - "
            "a mechanism, or a DOF released by every member at a node - is the usual cause; "
            "OpenSees' own message is on stdout.".format(case_tag, " '{}'".format(case_name) if case_name else "", status))
    ops.reactions()


def clear_case(ops, case_tag):
    ops.remove("loadPattern", case_tag)
    ops.wipeAnalysis()
    ops.reset()


__all__ = ["AnalysisError", "apply_case", "solve_case", "clear_case"]
