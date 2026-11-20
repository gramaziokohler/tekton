"""Tekton Apply Loads - put authored loads onto the analysis model.

Must run **after** TektonTranslate. Reason: point loads need nodes, member
loads need the members a physical beam was split into - both only come into
existence during translation. The authoring components therefore hand over
geometric descriptions (point, element GUID), and resolving those to model IDs
happens here.

Area loads also stay in the model as such (StructuralAreaLoad): RFEM can
carry them as load transfer surfaces when the Area Load asks for it.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Apply Loads"  # type: ignore # noqa: F821


def _repo_candidates(explicit):
    """Where to look for the monorepo, cheapest and most certain first.

    Only `isdir` calls - never a filesystem search, this runs on every solve.
    The document guess is what makes a definition stored inside the repo work
    with nothing configured at all; the cache file is what makes the path
    survive a Rhino restart. Mirrors tekton_gh.env.discover_repo_root, which
    cannot be imported yet - finding the repo is what makes it importable.
    """
    yield explicit
    yield os.environ.get("TEKTON_REPO")
    try:
        document = ghenv.Component.OnPingDocument()  # type: ignore # noqa: F821
        current = os.path.dirname(document.FilePath) if document and document.FilePath else None
        for _ in range(8):
            if not current:
                break
            yield current
            parent = os.path.dirname(current)
            current = None if parent == current else parent
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.expanduser("~"), ".tekton", "repo-root")) as handle:
            yield handle.read()
    except Exception:
        pass
    for guess in ("~/Documents/GitHub/tekton", "~/Documents/git/tekton", "~/git/tekton",
                  "~/GitHub/tekton", "~/Developer/tekton", "~/src/tekton", "~/tekton",
                  "~/Documents/tekton", "~/Desktop/tekton"):
        yield guess


def _remember_repo(root):
    """Write the root down so the next Rhino session finds it by itself."""
    try:
        directory = os.path.join(os.path.expanduser("~"), ".tekton")
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, "repo-root"), "w") as handle:
            handle.write(root)
    except Exception:
        pass


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable."""
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and compas_timber_fea, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("compas_timber_fea") and importlib.util.find_spec("tekton_gh"):
            return None
    root = None
    for candidate in _repo_candidates(explicit_repo):
        candidate = str(candidate).strip() if candidate else ""
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
    _remember_repo(root)
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
    import copy

    # Work on a copy. Grasshopper hands over the very object TektonTranslate
    # holds; when only a load changes, this re-solves without Translate and
    # would stack the loads onto those of the previous solve.
    structural = copy.deepcopy(structural)
    from compas_timber_fea.core.model import StructuralMemberLoad, StructuralPointLoad, StructuralSurfaceLoad

    tol = 0.01 if tolerance is None else float(tolerance)

    # Scaling: the authoring components work in document units (Rhino,
    # typically mm), the neutral model in metres.
    units = getattr(structural, "source_units", "m")
    to_meters = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}.get(units, 1.0)

    next_point_id = max([load.id for load in structural.point_loads] or [0]) + 1
    next_member_id = max([load.id for load in structural.member_loads] or [0]) + 1
    next_surface_id = max([load.id for load in structural.surface_loads] or [0]) + 1
    # Plate GUID -> the surfaces it became, the same idea as by_source for beams.
    by_surface_source = {}
    for surface in structural.surfaces:
        by_surface_source.setdefault(str(surface.source_element_id), []).append(surface.id)

    # Element GUID -> all members that came out of it. A beam is split during
    # idealisation; a member load has to go onto every piece.
    by_source = {}
    for member in structural.members:
        by_source.setdefault(str(member.source_element_id), []).append(member.id)

    applied_points = 0
    applied_members = 0
    applied_surfaces = 0
    applied_areas = 0

    for load in loads or []:
        # The load components hand over a carrier with the dict in `.spec`
        # (a bare dict would arrive unpacked into its keys); a plain dict,
        # from a script, is taken as it is.
        load = getattr(load, "spec", load)
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
            from compas_timber_fea.core.load_distribution import element_ranges, split_range

            start = float(load.get("dist_start", 0.0))
            end = float(load.get("dist_end", 1.0))
            hit = 0
            for element_id in load.get("element_ids", []):
                member_ids = by_source.get(str(element_id), [])
                if not member_ids:
                    report.append("Element {} has no members in the analysis model.".format(element_id))
                    continue
                # start/end are relative to the beam, but the beam is a chain
                # of members now - map the stretch onto the pieces covering it.
                if start <= 0.0 and end >= 1.0:
                    pieces = [(member_id, 0.0, 1.0) for member_id in member_ids]
                else:
                    pieces = split_range(element_ranges(structural, member_ids), start, end)
                for member_id, dist_start, dist_end in pieces:
                    structural.member_loads.append(
                        StructuralMemberLoad(
                            id=next_member_id,
                            member_id=member_id,
                            load_case_id=load.get("load_case_id", 1),
                            force=Vector(*load["force"]),
                            dist_start=dist_start,
                            dist_end=dist_end,
                        )
                    )
                    next_member_id += 1
                    hit += 1
            if hit:
                applied_members += hit

        elif load.get("kind") == "area":
            # The work lives in the library (reloads without rebuilding this component).
            from compas_timber_fea.core.load_distribution import apply_area_load

            info = apply_area_load(structural, load, to_meters=to_meters, report=report)
            applied_members += info["members"]
            applied_areas += 1
            next_member_id = max([m.id for m in structural.member_loads] or [0]) + 1

        elif load.get("kind") == "surface":
            from compas.geometry import Vector

            hit = 0
            for element_id in load.get("element_ids", []):
                surface_ids = by_surface_source.get(str(element_id), [])
                if not surface_ids:
                    report.append("Plate {} has no surface in the analysis model.".format(element_id))
                    continue
                for surface_id in surface_ids:
                    structural.surface_loads.append(
                        StructuralSurfaceLoad(
                            id=next_surface_id,
                            surface_id=surface_id,
                            load_case_id=load.get("load_case_id", 1),
                            pressure=Vector(*load["pressure"]),
                            projected=bool(load.get("projected", False)),
                        )
                    )
                    next_surface_id += 1
                    hit += 1
            if hit:
                applied_surfaces += hit

    for combination in combinations or []:
        structural.load_combinations.append(combination)

    report.insert(0, "{} point loads, {} member loads, {} plate loads applied{}.".format(
        applied_points, applied_members, applied_surfaces,
        " ({} area load(s) on beam grids among the member loads)".format(applied_areas) if applied_areas else ""))
    if combinations:
        report.insert(1, "{} combination(s) taken over.".format(len(combinations)))


for line in report:
    print(line)
