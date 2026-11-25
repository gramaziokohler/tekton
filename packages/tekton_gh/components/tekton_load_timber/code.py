"""Tekton Load Timber - read a compas_timber model from JSON.

The design model, not the analysis one: beams, plates and their joints as
COMPAS Timber saved them. Everything downstream (Translate, Support, Run)
starts from a TimberModel, and until now the only way to get one onto the
canvas from a file was a Python component of your own.

The counterpart for the *neutral* model is `Tekton Load Model`.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Load Timber"  # type: ignore # noqa: F821


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


def _extent(beams, plates):
    """Largest span of the model, in whatever units it was authored in.

    Cheap: the centreline endpoints and plate outline corners, nothing else.
    """
    xs, ys, zs = [], [], []
    for beam in beams:
        line = getattr(beam, "centerline", None)
        if line is not None:
            for point in (line.start, line.end):
                xs.append(point.x)
                ys.append(point.y)
                zs.append(point.z)
    for plate in plates:
        outline = getattr(plate, "outline_a", None)
        for point in list(outline or []):
            xs.append(point[0])
            ys.append(point[1])
            zs.append(point[2])
    if not xs:
        return None
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _unit_guess(extent):
    """What unit an extent of this size suggests.

    A building is tens of metres or tens of thousands of millimetres. The two
    are three orders apart, so the guess is safe in the middle and honest at
    the edges - it is printed as a hint, never acted on.
    """
    if extent < 1e-6:
        return "a single point - nothing to measure"
    if extent > 1000.0:
        return "millimetres (a {:.0f} m building)".format(extent / 1000.0)
    if extent > 2.0:
        return "metres"
    return "unclear at this size - check before translating"

# --------------------- INPUTS ---------------------
filepath: str  # type: ignore
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

model = None
info = []

if not filepath:
    _warn("filepath is needed.")
elif not os.path.isfile(os.path.expanduser(filepath)):
    _warn("File not found: {}".format(filepath))
else:
    _setup(repo)
    from compas.data import json_load

    loaded = json_load(os.path.expanduser(filepath))

    # A COMPAS JSON holds whatever was serialised into it. Saying what came
    # back beats a later failure three components downstream with a message
    # about a missing attribute.
    if not hasattr(loaded, "beams"):
        _warn(
            "That file holds a {}, not a TimberModel. If it is a neutral "
            "model, use Tekton Load Model instead.".format(type(loaded).__name__)
        )
    else:
        model = loaded
        beams = list(model.beams)
        plates = list(getattr(model, "plates", None) or [])
        joints = list(getattr(model, "joints", None) or [])

        info = [
            "Beams: {}".format(len(beams)),
            "Plates: {}".format(len(plates)),
            "Joints: {}".format(len(joints)),
        ]

        # The units a timber model was authored in are not recorded in the
        # file, and getting them wrong is the classic silent failure: a model
        # in millimetres translated as metres solves as a 4 km beam. So
        # measure the model and say what it looks like, rather than guess.
        extent = _extent(beams, plates)
        if extent is not None:
            info.append("Largest dimension: {:.3g} units".format(extent))
            info.append("Looks like: {}".format(_unit_guess(extent)))

        if not beams and not plates:
            _warn("The model holds no beams and no plates.")

for line in info:
    print(line)
