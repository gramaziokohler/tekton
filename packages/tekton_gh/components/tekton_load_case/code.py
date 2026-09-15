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
    from tekton_gh.rhino_io import attach_value_list

    attach_value_list(ghenv, ['PERMANENT', 'VARIABLE', 'SNOW', 'WIND'], param_index=1, nickname="Category")  # type: ignore # noqa: F821
except Exception:
    pass

_setup()
from compas_timber_fea.core.model import StructuralLoadCase

VALID = ("PERMANENT", "VARIABLE", "SNOW", "WIND")
action = (category or "PERMANENT").upper()
if action not in VALID:
    _warn("Unknown category '{}'. Allowed: {}. PERMANENT is used instead.".format(action, ", ".join(VALID)))
    action = "PERMANENT"

load_case = StructuralLoadCase(
    id=int(id) if id else 1,
    name=name or "Load Case",
    action_category=action,
    self_weight=bool(self_weight),
)

print("Load case {}: '{}' ({}{})".format(
    load_case.id, load_case.name, load_case.action_category,
    ", self-weight" if load_case.self_weight else ""))
