"""Tekton Load Case - define a load case.

Load cases are the containers that loads and combinations refer to. The
translator creates only one by itself (self-weight); everything else comes
from here.

Careful: the Dlubal importer still ignores the neutral model's load cases and
uses a hard-wired catalogue (priority 1 in docs/handoff.md). Until that is
fixed, what stands here does not necessarily arrive in RFEM.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Load Case"  # type: ignore # noqa: F821


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
name: str  # type: ignore
category: str  # type: ignore
self_weight: bool  # type: ignore
id: int  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'category' the moment the component lands on the canvas. Needs
# the repo path for the import; without it the menu simply does not appear
# and TektonInfo says what is missing.
try:
    _setup()
    from compas_timber_fea.core.load_catalogue import category_names
    from tekton_gh.rhino_io import attach_value_list

    attach_value_list(ghenv, category_names(), param_index=1, nickname="Category")  # type: ignore # noqa: F821
except Exception:
    pass

_setup()
from compas_timber_fea.core.load_catalogue import CATEGORIES  # noqa: E402
from compas_timber_fea.core.load_catalogue import category as _category  # noqa: E402
from compas_timber_fea.core.load_catalogue import key_from_name  # noqa: E402
from compas_timber_fea.core.model import StructuralLoadCase  # noqa: E402

# The drop-down hands over "A - Imposed - domestic, residential"; a typed
# value is just the key. Both end up as the key.
action = key_from_name(category) if category else "PERMANENT"
if action not in CATEGORIES:
    _warn(
        "Unknown category '{}'. PERMANENT is used instead. Available: {}.".format(
            action, ", ".join(sorted(CATEGORIES))))
    action = "PERMANENT"

load_case = StructuralLoadCase(
    id=int(id) if id else 1,
    name=name or "Load Case",
    action_category=action,
    self_weight=bool(self_weight),
)

_entry = _category(action)
print("Load case {}: '{}' ({}{})".format(
    load_case.id, load_case.name, load_case.action_category,
    ", self-weight" if load_case.self_weight else ""))
print("  {}".format(_entry.name))
print("  psi_0 {:.2f}  psi_1 {:.2f}  psi_2 {:.2f}  gamma {:.2f}".format(
    _entry.psi_0, _entry.psi_1, _entry.psi_2, _entry.gamma_unfavourable))
print("  duration for k_mod: {}".format(_entry.load_duration))
if _entry.note:
    print("  note: {}".format(_entry.note))
print("  EN 1990 recommended values - NOT verified by an engineer, and not a national annex.")
