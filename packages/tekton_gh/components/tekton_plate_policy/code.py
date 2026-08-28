"""Tekton Plate Policy — Kopplung von Plattenraendern.

Gelenkige Kante (Default) oder durchlaufend. Pendant zur Joint Policy
fuer den Plattenpfad.

span_direction ist bei Holz nicht optional: Plattenwerkstoffe sind
orthotrop (E0 zu E90 unterscheiden sich um etwa Faktor 30). Ohne
festgelegte Tragrichtung sind Plattenergebnisse nicht interpretierbar.

TODO(scaffold): Die Orthotropie-Richtung fehlt im Datenmodell noch
(docs/handoff.md, Punkt 3); der Input wird bisher nur protokolliert.
"""
# venv: tekton
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Plate Policy"  # type: ignore # noqa: F821


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
preset: str  # type: ignore
span_direction = span_direction  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.joint_policy import PlateConnectionPolicy

key = (preset or "hinged").lower()
if key == "continuous":
    policy = PlateConnectionPolicy.continuous()
elif key == "hinged":
    policy = PlateConnectionPolicy()
else:
    _warn("Unbekanntes Preset '{}'. Erlaubt: hinged, continuous.".format(key))
    policy = PlateConnectionPolicy()

print("Plattenkanten: {} (Default {})".format(key, policy.default.name))

if span_direction is None:
    _warn(
        "Keine Tragrichtung gesetzt. Bei orthotropen Plattenwerkstoffen sind "
        "die Ergebnisse dann nicht eindeutig interpretierbar."
    )
else:
    print("Tragrichtung: ({:.3f}, {:.3f}, {:.3f}) — TODO: wird noch nicht ins Modell geschrieben.".format(
        span_direction.X, span_direction.Y, span_direction.Z))
