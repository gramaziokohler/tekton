"""Tekton Load Model — neutrales Modell aus JSON lesen.

Holt ein gespeichertes Modell samt Ergebnissen zurueck auf den Canvas:
einen frueheren Rechenlauf, oder das, was der Statiker zurueckschickt.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Load"  # type: ignore # noqa: F821


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
filepath: str  # type: ignore
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

structural = None
info = []

if not filepath:
    _warn("filepath wird gebraucht.")
elif not os.path.isfile(os.path.expanduser(filepath)):
    _warn("Datei nicht gefunden: {}".format(filepath))
else:
    _setup(repo)
    from compas_timber_fea.core.model import StructuralModel

    structural = StructuralModel.from_json(os.path.expanduser(filepath))

    results = getattr(structural, "results", {}) or {}
    info = [
        "Knoten: {}".format(len(structural.nodes)),
        "Staebe: {}".format(len(structural.members)),
        "Flaechen: {}".format(len(structural.surfaces)),
        "Lager: {}".format(len(structural.supports)),
        "Lastfaelle: {}".format(len(structural.load_cases)),
        "Ergebnissaetze: {}".format(len(results)),
        "Einheiten der Quelle: {}".format(getattr(structural, "source_units", "?")),
    ]

for line in info:
    print(line)
