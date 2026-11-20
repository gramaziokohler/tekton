"""Tekton Inspect - look at the analysis model itself.

System lines, nodes, support symbols, release markers. For checking the
idealisation before calculating - deliberately separate from the result
display.

This is the view that shows whether the idealisation did what you expected:
where it split, where the releases sit.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Inspect"  # type: ignore # noqa: F821


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
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
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
show = show  # type: ignore # noqa: F821
scale: float  # type: ignore

# --------------------- SCRIPT ---------------------

members = []
nodes = []
supports = []
releases = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    import Rhino.Geometry as rg
    from tekton_gh.rhino_io import member_lines

    units = getattr(structural, "source_units", "m")
    factor = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(units, 1.0)
    symbol = (scale if scale else 0.1) * factor

    wanted = set(s.lower() for s in (show or ["members", "nodes", "supports", "releases"]))
    node_points = {n.id: n.point for n in structural.nodes}

    if "members" in wanted:
        members = member_lines(structural, scale=factor)

    if "nodes" in wanted:
        nodes = [rg.Point3d(p[0] * factor, p[1] * factor, p[2] * factor) for p in node_points.values()]

    if "supports" in wanted:
        # Supports as a small downward tick - enough to spot them.
        for support in structural.supports:
            for node_id in support.nodes:
                point = node_points.get(node_id)
                if point is None:
                    continue
                base = rg.Point3d(point[0] * factor, point[1] * factor, point[2] * factor)
                tip = rg.Point3d(base.X, base.Y, base.Z - symbol)
                supports.append(rg.Line(base, tip))

    if "releases" in wanted:
        # Releases as a short stroke at the member end where something is free.
        for member in structural.members:
            start, end = node_points.get(member.node_start), node_points.get(member.node_end)
            if start is None or end is None:
                continue
            for release, anchor, other in ((member.release_start, start, end),
                                           (member.release_end, end, start)):
                if release is None or release.is_rigid():
                    continue
                ax = rg.Point3d(anchor[0] * factor, anchor[1] * factor, anchor[2] * factor)
                ox = rg.Point3d(other[0] * factor, other[1] * factor, other[2] * factor)
                direction = ox - ax
                if direction.Length == 0:
                    continue
                direction.Unitize()
                releases.append(rg.Line(ax, ax + direction * symbol * 0.5))

    print("{} members, {} nodes, {} supports, {} release markers".format(
        len(members), len(nodes), len(supports), len(releases)))
