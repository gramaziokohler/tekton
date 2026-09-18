"""Tekton Support Nodes - supports straight onto the analysis model.

The translator finds supports by reading ``support_points`` off beams. Plates
have no such path, so a plate model arrives at the backend unsupported - a
mechanism, which either fails loudly in the solver or, worse, produces numbers
nobody should trust.

This component closes that gap on the analysis side: pick nodes by a level or
by proximity to points, and give them a support. It has to run *after*
Translate, because before that there are no nodes.

For beams, prefer TektonSupport: marking the design model keeps the intent
with the element, and it survives a re-translate. This one is for plates, and
for the cases where the engineer wants to support a specific node.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Support Nodes"  # type: ignore # noqa: F821


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
    """Make compas_timber_fea importable."""
    root = None
    for candidate in _repo_candidates(explicit_repo):
        candidate = str(candidate).strip() if candidate else ""
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Put a component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then holds for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own, and
    # for the next Rhino session.
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
points = points  # type: ignore # noqa: F821
level: float  # type: ignore
support_type: str  # type: ignore
stiffness = stiffness  # type: ignore # noqa: F821
tolerance: float  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'support_type' the moment the component lands on the canvas. Needs
# the repo path for the import; without it the menu simply does not appear
# and TektonInfo says what is missing.
try:
    _setup()
    from tekton_gh.rhino_io import attach_value_list

    from compas_timber_fea.core.support_types import support_type_names

    attach_value_list(ghenv, support_type_names(), param_index=3, nickname="Support_type")  # type: ignore # noqa: F821
except Exception:
    pass

nodes = []
report = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    import Rhino.Geometry as rg
    from compas_timber_fea.core.model import StructuralSupport

    from compas_timber_fea.core.support_types import SUPPORT_TYPE_ORDER
    from compas_timber_fea.core.support_types import describe as _describe_support
    from compas_timber_fea.core.support_types import key_from_name
    from compas_timber_fea.core.support_types import stiffnesses

    # The catalogue carries all twelve named types plus the explicit and
    # spring paths; see core/support_types.py.
    kind = key_from_name(support_type) if support_type else "pinned"
    _springs = {}
    if stiffness:
        _values = [float(v) for v in stiffness]
        if len(_values) == 6:
            _explicit = _values
        else:
            _warn("'stiffness' needs 6 values (ux, uy, uz, rx, ry, rz); {} given - ignored.".format(len(_values)))
            _explicit = None
    else:
        _explicit = None

    try:
        _dofs = stiffnesses(kind, explicit=_explicit, springs=_springs)
    except ValueError as error:
        _warn("{} Using pinned.".format(error))
        kind = "pinned"
        _dofs = stiffnesses(kind)
    KINDS = {kind: _dofs}

    # The model is in metres, the canvas in document units.
    units = getattr(structural, "source_units", "m")
    to_meters = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}.get(units, 1.0)
    tol_m = (1.0 if tolerance is None else float(tolerance)) * to_meters

    selected = []
    if points:
        for point in points:
            target = (point.X * to_meters, point.Y * to_meters, point.Z * to_meters)
            best, best_distance = None, None
            for node in structural.nodes:
                distance = sum((node.point[i] - target[i]) ** 2 for i in range(3)) ** 0.5
                if best_distance is None or distance < best_distance:
                    best, best_distance = node, distance
            if best is not None and best_distance <= tol_m:
                selected.append(best)
            else:
                report.append(
                    "no node within {:.4g} m of ({:.3f}, {:.3f}, {:.3f}) - not supported".format(
                        tol_m, target[0], target[1], target[2]))
    elif level is not None:
        z = float(level) * to_meters
        selected = [n for n in structural.nodes if abs(n.point[2] - z) <= tol_m]
        if not selected:
            report.append("no node at z = {:.4g} m (tolerance {:.4g} m)".format(z, tol_m))
    else:
        _warn("Give either points or a level - otherwise there is nothing to support.")

    # Deduplicate: two points can land on the same node, and a node supported
    # twice would end up in two support groups.
    unique = []
    seen = set()
    for node in selected:
        if node.id not in seen:
            seen.add(node.id)
            unique.append(node)

    if unique:
        next_id = max([s.id for s in structural.supports] or [0]) + 1
        structural.supports.append(StructuralSupport(
            id=next_id,
            nodes=[n.id for n in unique],
            name="{} support (nodes)".format(kind.capitalize()),
            **KINDS[kind]
        ))
        scale = 1.0 / to_meters
        nodes = [rg.Point3d(n.point[0] * scale, n.point[1] * scale, n.point[2] * scale)
                 for n in unique]
        report.insert(0, "{} node(s) supported, type '{}'.".format(
            len(unique), "explicit" if _explicit else kind))
        report.insert(1, "  {}".format(_describe_support(KINDS[kind])))
    else:
        report.insert(0, "No node supported.")

for line in report:
    print(line)
