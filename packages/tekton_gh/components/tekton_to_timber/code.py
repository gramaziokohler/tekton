"""Tekton To Timber - rebuild the timber model from the analysis model.

The neutral model keeps everything a beam body needs: segments per source
GUID, section, orientation. So a StructuralModel that arrives on its own -
loaded from JSON, sent back by the engineer, straight from Run - becomes a
TimberModel again, with the original GUIDs and, when present, the results
attached as beam.attributes['analysis'].

Not rebuilt: joints. Their *types* are not in the neutral model (a butt is
not a lap), only that two beams connect. Beams come back as their blank
(the effective system line includes the blank extensions).
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "To Timber"  # type: ignore # noqa: F821


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
structural = structural  # type: ignore # noqa: F821
attach: bool  # type: ignore
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

model = None
report = []
connections = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup(repo)
    import importlib
    import compas_timber_fea.reconstruct
    importlib.reload(compas_timber_fea.reconstruct)
    from compas_timber_fea.reconstruct import beam_connectivity, structural_to_timber

    model, report = structural_to_timber(structural, attach_results=True if attach is None else bool(attach))
    connections = ["{} - {}".format(a[:8], b[:8]) for a, b, _joint in beam_connectivity(structural)]

    if not list(model.beams):
        _warn("No beams rebuilt - the members carry no source_element_id (not translated by Tekton?).")

for line in report:
    print(line)
