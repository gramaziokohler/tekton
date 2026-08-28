"""Tekton Material — Werkstoff waehlen.

Heute traegt das neutrale Modell nur einen Namens-String, den RFEM gegen
seine eigene Bibliothek aufloest ('C24 | EN 338:2016-04'). Fuer SAF und
erst recht fuer OpenSees/Abaqus reicht das nicht — die brauchen echte
Zahlen (E, G, Rohdichte).

TODO(scaffold): Sobald die Material-Dataclass mit Presets existiert
(discussion/materials.md), gibt diese Komponente ein Objekt statt eines
Strings aus, und die Overrides unten werden wirksam.
"""
# venv: tekton
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Material"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
grade: str  # type: ignore
E0_mean: float  # type: ignore
density: float  # type: ignore

# --------------------- SCRIPT ---------------------

material = grade or "C24"
info = ["Guete: {}".format(material)]

# TODO(scaffold): Platzhalter. Die Overrides werden erst wirksam, wenn das
# neutrale Modell echte Materialeigenschaften traegt statt eines Namens.
if E0_mean is not None:
    info.append("E0,mean-Ueberschreibung {} N/mm2 — noch WIRKUNGSLOS (Material ist heute nur ein Name).".format(E0_mean))
if density is not None:
    info.append("Rohdichte-Ueberschreibung {} kg/m3 — noch WIRKUNGSLOS.".format(density))

info.append("RFEM loest den Namen gegen seine Bibliothek auf; SAF setzt derzeit feste C24-Werte ein.")

for line in info:
    print(line)
