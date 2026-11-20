"""Tekton Plate Policy - coupling of plate edges.

Hinged edge (default) or continuous. Counterpart to the Joint Policy for the
plate path.

span_direction is not optional for timber: panel materials are orthotropic (E0
and E90 differ by roughly a factor of 30). And it decides how results are to be
read - RFEM's m_x follows the surface axes, so without a fixed direction the
moments cannot be interpreted.

The translator derives the direction from the plate frame itself
(`frame.xaxis`, the geometric principal axis). This input is an **override**
for the case where the grain direction differs from that - it is written onto
all surfaces of the model. In the plate graph design this later becomes
`SurfaceRegion.frame.x`; the vector therefore moves into the chain layer
without rework.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Plate Policy"  # type: ignore # noqa: F821


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
preset: str  # type: ignore
span_direction = span_direction  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.joint_policy import PlateConnectionPolicy

from tekton_gh.rhino_io import attach_value_list, value_list_items

attach_value_list(ghenv, ["hinged", "continuous"], param_index=0, nickname="Preset")  # type: ignore # noqa: F821

for _line in value_list_items(ghenv, ["hinged", "continuous"]):  # type: ignore # noqa: F821
    print(_line)

key = (preset or "hinged").lower().strip('"')
if key == "continuous":
    policy = PlateConnectionPolicy.continuous()
elif key == "hinged":
    policy = PlateConnectionPolicy()
else:
    _warn("Unknown preset '{}'. Allowed: hinged, continuous.".format(key))
    policy = PlateConnectionPolicy()

print("Plate edges: {} (default {})".format(key, policy.default.name))

# The span direction hangs off the policy because it is authored together
# with it; TektonTranslate writes it onto the surfaces after translating.
# Writing it straight into the model here would not work - at this point no
# surface exists yet.
if span_direction is None:
    policy.span_direction_override = None
    print("Span direction: derived from the plate frame (geometric principal axis).")
else:
    vector = [float(span_direction.X), float(span_direction.Y), float(span_direction.Z)]
    length = sum(v * v for v in vector) ** 0.5
    if length < 1e-9:
        _warn("Span direction is a zero vector - ignored.")
        policy.span_direction_override = None
    else:
        policy.span_direction_override = [v / length for v in vector]
        print("Span direction (override, normalised): ({:.3f}, {:.3f}, {:.3f})".format(
            *policy.span_direction_override))
