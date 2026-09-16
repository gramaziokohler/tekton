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


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
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
