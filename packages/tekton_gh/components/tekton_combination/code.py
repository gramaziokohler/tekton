"""Tekton Load Combination - load combination.

Combines load cases with partial safety factors. Manual work today; later an
EC0 generator (permanent/variable, psi factors) would be the real convenience
win.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Combination"  # type: ignore # noqa: F821


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
load_cases = load_cases  # type: ignore # noqa: F821
factors = factors  # type: ignore # noqa: F821
combination_type: str  # type: ignore

# --------------------- SCRIPT ---------------------

combination = None

if not load_cases or not factors:
    _warn("load_cases and factors are both needed.")
elif len(load_cases) != len(factors):
    _warn("load_cases ({}) and factors ({}) must be the same length.".format(len(load_cases), len(factors)))
else:
    _setup()
    from compas_timber_fea.core.releases import LoadCombination

    combination = LoadCombination(
        id=1,
        name=name or "Combination",
        factors={getattr(lc, "id", i + 1): float(f) for i, (lc, f) in enumerate(zip(load_cases, factors))},
        combination_type=(combination_type or "ULS").upper(),
    )
    print("{} '{}': {}".format(combination.combination_type, combination.name, combination.factors))
