"""Tekton Upgrade - bring every Tekton component in this definition up to date.

A component you placed keeps the script it was placed with, even after a
Tekton update. Press the button once: each Tekton component in the document
(except this one) is replaced by its current version at the same place, with
its nickname and wires. Inputs or outputs that were renamed or removed lose
their wire - the report names them, reconnect those by hand. Tekton Run
loses its cached results in the swap; press its button again.

The swap runs after the solve, on the UI thread, never inside it: touching
the canvas during a solve is what crashed Rhino before. See
`tekton_gh.upgrade` for the guards.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Upgrade"  # type: ignore # noqa: F821


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
upgrade: bool  # type: ignore
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

report = []

_setup(repo)
import importlib
import tekton_gh.upgrade
importlib.reload(tekton_gh.upgrade)
from tekton_gh.upgrade import last_report, schedule_upgrade, user_object_folder

folder = user_object_folder()
if not folder:
    _warn("Tekton UserObjects folder not found - are the components installed?")

if upgrade:
    scheduled, message = schedule_upgrade(ghenv, folder)  # type: ignore # noqa: F821
    report = [message]
    if not scheduled:
        _warn(message)
else:
    report = last_report(ghenv) or ["Ready. Press the button to replace every Tekton component with its installed template."]  # type: ignore # noqa: F821
    if folder:
        report.append("Templates: {}".format(folder))

for line in report:
    print(line)
