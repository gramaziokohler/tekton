"""Tekton Support - mark support points on beams.

Writes `beam.attributes['support_points']`. Today that is the only way the
translator finds supports: per beam it looks for the points lying on the axis
within the tolerance, and creates pinned support nodes there.

The tolerance is in model units, not in metres - so in a mm document 1e-4 is a
tenth of a micrometre. Usually you want a larger value here.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Support"  # type: ignore # noqa: F821


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
    """Make tekton_core + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and tekton_core, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("tekton_core") and importlib.util.find_spec("tekton_gh"):
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
    for package in ("tekton_gh", "tekton_core"):
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
model = model  # type: ignore # noqa: F821  TimberModel
points = points  # type: ignore # noqa: F821
support_type: str  # type: ignore
tolerance: float  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'support_type' the moment the component lands on the canvas. Needs
# the repo path for the import; without it the menu simply does not appear
# and TektonInfo says what is missing.
try:
    _setup()
    from tekton_gh.rhino_io import attach_value_list

    from tekton_core.core.support_types import support_type_names

    attach_value_list(ghenv, support_type_names(), param_index=2, nickname="Support_type")  # type: ignore # noqa: F821
except Exception:
    pass

found = []
missed = []

if model is None or not points:
    _warn("model and points are both needed.")
else:
    _setup()

    tol = tolerance if tolerance else 1e-4

    from tekton_core.core.support_types import SUPPORT_TYPE_ORDER
    from tekton_core.core.support_types import describe as _describe_support
    from tekton_core.core.support_types import key_from_name
    from tekton_core.core.support_types import stiffnesses

    support_type = key_from_name(support_type) if support_type else "pinned"
    try:
        _dofs = stiffnesses(support_type)
    except ValueError as error:
        _warn("{} Using pinned.".format(error))
        support_type = "pinned"
        _dofs = stiffnesses(support_type)

    # Map points to beams: a point belongs to the beam on whose centreline it
    # lies (within the tolerance).
    for point in points:
        px, py, pz = point.X, point.Y, point.Z
        matched = False
        for beam in model.beams:
            line = beam.centerline
            start, end = line.start, line.end
            # Distance point <-> segment.
            dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
            length_sq = dx * dx + dy * dy + dz * dz
            if length_sq == 0:
                continue
            t = ((px - start[0]) * dx + (py - start[1]) * dy + (pz - start[2]) * dz) / length_sq
            t = max(0.0, min(1.0, t))
            cx, cy, cz = start[0] + t * dx, start[1] + t * dy, start[2] + t * dz
            distance = ((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2) ** 0.5
            if distance <= tol:
                existing = beam.attributes.get("support_points") or []
                # The type travels with the point, so one beam can carry a
                # pinned and a roller support without them merging.
                existing.append([px, py, pz, support_type])
                beam.attributes["support_points"] = existing
                found.append(point)
                matched = True
                break
        if not matched:
            missed.append(point)

    if missed:
        _warn(
            "{} of {} points lie on no beam axis (tolerance {}). "
            "Those points create NO support.".format(len(missed), len(points), tol)
        )

    print("{} support points set, {} unmatched.".format(len(found), len(missed)))
