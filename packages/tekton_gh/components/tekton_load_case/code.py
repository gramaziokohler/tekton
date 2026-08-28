"""Tekton Load Case — Lastfall definieren.

Lastfaelle sind die Container, auf die sich Lasten und Kombinationen
beziehen. Der Translator legt von sich aus nur einen an (Eigengewicht);
alles Weitere kommt von hier.

Achtung: der Dlubal-Importer ignoriert die Lastfaelle des neutralen
Modells derzeit noch und nutzt einen fest verdrahteten Katalog
(Prioritaet 1 in docs/handoff.md). Bis das behoben ist, kommt in RFEM
nicht unbedingt an, was hier steht.
"""
# venv: tekton
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Load Case"  # type: ignore # noqa: F821


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
        raise RuntimeError("Tekton-Repo nicht gefunden — siehe TektonInfo.")
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

_setup()
from compas_timber_fea.core.model import StructuralLoadCase

VALID = ("PERMANENT", "VARIABLE", "SNOW", "WIND")
action = (category or "PERMANENT").upper()
if action not in VALID:
    _warn("Unbekannte Kategorie '{}'. Erlaubt: {}. Es wird PERMANENT verwendet.".format(action, ", ".join(VALID)))
    action = "PERMANENT"

load_case = StructuralLoadCase(
    id=int(id) if id else 1,
    name=name or "Load Case",
    action_category=action,
    self_weight=bool(self_weight),
)

print("Lastfall {}: '{}' ({}{})".format(
    load_case.id, load_case.name, load_case.action_category,
    ", Eigengewicht" if load_case.self_weight else ""))
