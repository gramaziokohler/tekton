"""Tekton Apply Loads - put authored loads onto the analysis model.

Must run **after** TektonTranslate. Reason: point loads need nodes, member
loads need the members a physical beam was split into - both only come into
existence during translation. The authoring components therefore hand over
geometric descriptions (point, element GUID), and resolving those to model IDs
happens here.

Careful: the Dlubal importer still ignores the neutral model's load cases and
uses a hard-wired catalogue (priority 1 in docs/handoff.md). Until that is
fixed, what is set here does not necessarily arrive in RFEM.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Apply Loads"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable."""
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )


# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
loads = loads  # type: ignore # noqa: F821
combinations = combinations  # type: ignore # noqa: F821
tolerance: float  # type: ignore

# --------------------- SCRIPT ---------------------

report = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    from compas_timber_fea.core.model import StructuralMemberLoad, StructuralPointLoad

    tol = 0.01 if tolerance is None else float(tolerance)

    # Scaling: the authoring components work in document units (Rhino,
    # typically mm), the neutral model in metres.
    units = getattr(structural, "source_units", "m")
    to_meters = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}.get(units, 1.0)

    next_point_id = max([load.id for load in structural.point_loads] or [0]) + 1
    next_member_id = max([load.id for load in structural.member_loads] or [0]) + 1

    # Element GUID -> all members that came out of it. A beam is split during
    # idealisation; a member load has to go onto every piece.
    by_source = {}
    for member in structural.members:
        by_source.setdefault(str(member.source_element_id), []).append(member.id)

    applied_points = 0
    applied_members = 0

    for load in loads or []:
        if not isinstance(load, dict):
            report.append("Skipped unknown load entry: {}".format(type(load).__name__))
            continue

        if load.get("kind") == "point":
            position = [value * to_meters for value in load["position"]]
            # Find the nearest node - the load hangs off a point, not an ID.
            best_id, best_distance = None, None
            for node in structural.nodes:
                distance = sum((node.point[i] - position[i]) ** 2 for i in range(3)) ** 0.5
                if best_distance is None or distance < best_distance:
                    best_id, best_distance = node.id, distance

            if best_id is None or best_distance > tol:
                report.append(
                    "Point load with no node in range (nearest: {:.4g} m, tolerance {:.4g} m) "
                    "- NOT applied.".format(best_distance if best_distance is not None else -1, tol)
                )
                continue

            from compas.geometry import Vector

            structural.point_loads.append(
                StructuralPointLoad(
                    id=next_point_id,
                    node_id=best_id,
                    load_case_id=load.get("load_case_id", 1),
                    force=Vector(*load["force"]),
                    moment=Vector(*load.get("moment", [0.0, 0.0, 0.0])),
                )
            )
            next_point_id += 1
            applied_points += 1

        elif load.get("kind") == "member":
            from compas.geometry import Vector

            hit = 0
            for element_id in load.get("element_ids", []):
                member_ids = by_source.get(str(element_id), [])
                if not member_ids:
                    report.append("Element {} has no members in the analysis model.".format(element_id))
                    continue
                for member_id in member_ids:
                    structural.member_loads.append(
                        StructuralMemberLoad(
                            id=next_member_id,
                            member_id=member_id,
                            load_case_id=load.get("load_case_id", 1),
                            force=Vector(*load["force"]),
                            dist_start=load.get("dist_start", 0.0),
                            dist_end=load.get("dist_end", 1.0),
                        )
                    )
                    next_member_id += 1
                    hit += 1
            if hit:
                applied_members += hit

    for combination in combinations or []:
        structural.load_combinations.append(combination)

    report.insert(0, "{} point loads, {} member loads applied.".format(applied_points, applied_members))
    if combinations:
        report.insert(1, "{} combination(s) taken over.".format(len(combinations)))

    report.append(
        "Note: the Dlubal importer still uses a hard-wired load catalogue - "
        "what stands here may not arrive in RFEM "
        "(docs/handoff.md, item 1)."
    )

for line in report:
    print(line)
