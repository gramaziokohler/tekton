"""Tekton Plate Policy — Kopplung von Plattenraendern.

Gelenkige Kante (Default) oder durchlaufend. Pendant zur Joint Policy
fuer den Plattenpfad.

span_direction ist bei Holz nicht optional: Plattenwerkstoffe sind
orthotrop (E0 zu E90 unterscheiden sich um etwa Faktor 30). Und sie
entscheidet, wie Ergebnisse zu lesen sind — RFEMs m_x folgt den
Flaechenachsen, ohne fixierte Richtung sind die Momente nicht
interpretierbar.

Der Translator leitet die Richtung selbst aus dem Plattenframe ab
(`frame.xaxis`, geometrische Hauptachse). Dieser Input ist ein
**Override** fuer den Fall, dass die Faserrichtung davon abweicht — er
wird auf alle Flaechen des Modells geschrieben. Im Plattengraph-Design
ist das spaeter `SurfaceRegion.frame.x`; der Vektor wandert also ohne
Umbau in die Chain-Schicht.
"""
# venv: tekton-test
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

# Die Tragrichtung haengt an der Policy, weil sie zusammen mit ihr
# authoriert wird; TektonTranslate schreibt sie nach dem Uebersetzen auf
# die Flaechen. Sie hier direkt ins Modell zu schreiben ginge nicht — zu
# diesem Zeitpunkt existiert noch keine Flaeche.
if span_direction is None:
    policy.span_direction_override = None
    print("Tragrichtung: aus dem Plattenframe abgeleitet (geometrische Hauptachse).")
else:
    vector = [float(span_direction.X), float(span_direction.Y), float(span_direction.Z)]
    length = sum(v * v for v in vector) ** 0.5
    if length < 1e-9:
        _warn("Tragrichtung ist ein Nullvektor — ignoriert.")
        policy.span_direction_override = None
    else:
        policy.span_direction_override = [v / length for v in vector]
        print("Tragrichtung (Override, normiert): ({:.3f}, {:.3f}, {:.3f})".format(
            *policy.span_direction_override))
