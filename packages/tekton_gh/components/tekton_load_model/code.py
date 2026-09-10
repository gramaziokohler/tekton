"""Tekton Load Model - read a neutral model from JSON.

Brings a saved model back onto the canvas together with its results: an
earlier calculation run, or whatever the engineer sends back.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Load"  # type: ignore # noqa: F821


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
filepath: str  # type: ignore
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

structural = None
info = []

if not filepath:
    _warn("filepath is needed.")
elif not os.path.isfile(os.path.expanduser(filepath)):
    _warn("File not found: {}".format(filepath))
else:
    _setup(repo)
    from compas_timber_fea.core.model import StructuralModel

    structural = StructuralModel.from_json(os.path.expanduser(filepath))

    results = getattr(structural, "results", {}) or {}
    info = [
        "Nodes: {}".format(len(structural.nodes)),
        "Members: {}".format(len(structural.members)),
        "Surfaces: {}".format(len(structural.surfaces)),
        "Supports: {}".format(len(structural.supports)),
        "Load cases: {}".format(len(structural.load_cases)),
        "Result sets: {}".format(len(results)),
        "Source units: {}".format(getattr(structural, "source_units", "?")),
    ]

for line in info:
    print(line)
