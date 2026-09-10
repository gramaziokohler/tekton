"""Tekton Load Combination — Lastkombination.

Kombiniert Lastfaelle mit Teilsicherheitsbeiwerten. Heute Handarbeit;
spaeter waere ein EC0-Generator (staendig/veraenderlich, psi-Beiwerte)
der eigentliche Komfortgewinn.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Combination"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea + tekton_gh importierbar machen.

    Siehe TektonInfo, wenn das fehlschlaegt. Der Purge ist noetig, weil in
    Rhino womoeglich schon ein anderes compas_timber geladen ist (das
    offizielle Plugin, 1.0.5), das kein `compas_timber.structural` kennt.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton-Repo nicht gefunden. Eine Komponente mit 'repo'-Input "
            "(TektonInfo, TektonTranslate, TektonBackend) einmal auf dem Canvas "
            "setzen — der Pfad gilt dann fuer die ganze Sitzung. Siehe TektonInfo."
        )
    # Fuer die Komponenten ohne eigenen repo-Input hinterlegen.
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
    _warn("load_cases und factors werden gebraucht.")
elif len(load_cases) != len(factors):
    _warn("load_cases ({}) und factors ({}) muessen gleich lang sein.".format(len(load_cases), len(factors)))
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
