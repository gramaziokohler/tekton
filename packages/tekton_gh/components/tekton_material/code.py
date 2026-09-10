"""Tekton Material — Werkstoff aus der Bibliothek, mit Überschreibungen.

Ein Güteklassen-Name ist ein Schlüssel, kein Material. RFEM löst Namen zwar
gegen seine eigene Bibliothek auf, aber SAF will die Zahlen im Blatt, und
OpenSees/Abaqus haben gar keine Bibliothek. Darum trägt das neutrale Modell
die physikalischen Eigenschaften, und diese Komponente liefert sie.

Die Presets stammen aus `compas_timber_fea.core.materials` (EN 338 für
Vollholz, EN 14080 für Brettschichtholz) — eine Quelle für GH, GUI und CLI.

Überschreibungen sind der Normalfall bei geprüftem Material: Preset als
Ausgangspunkt, einzelne Werte ersetzt. Sie wandern mit dem Modell und stehen
im Annahmenprotokoll.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Material"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea importierbar machen."""
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
grade: str  # type: ignore
E0_mean: float  # type: ignore
density: float  # type: ignore

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.materials import PRESETS, Material  # noqa: E402

name = (grade or "C24").strip()

overrides = {}
if E0_mean is not None:
    overrides["E0_mean"] = float(E0_mean)
if density is not None:
    overrides["density_mean"] = float(density)

if name in PRESETS:
    material = Material.from_preset(name, **overrides)
else:
    # Unbekannte Guete: Eigenschaften werden geliehen, aber sichtbar als
    # Annahme markiert — lieber eine benannte Annahme als eine stille.
    material = Material.resolve(name)
    if overrides:
        from dataclasses import replace

        material = replace(material, **overrides)
    _warn(
        "Unbekannte Guete '{}'. Eigenschaften von C24 uebernommen und als Annahme "
        "markiert. Bekannt: {}.".format(name, ", ".join(sorted(PRESETS)))
    )

info = [
    "{} ({})".format(material.name, material.standard),
    "E0,mean {:.0f} N/mm2 | E90,mean {:.0f} | G {:.0f}".format(
        material.E0_mean, material.E90_mean, material.G_mean),
    "Rohdichte {:.0f} kg/m3 (charakteristisch {:.0f})".format(
        material.density_mean, material.density_k),
    "f_m,k {:.1f} | f_t0,k {:.1f} | f_c0,k {:.1f} | f_v,k {:.1f} N/mm2".format(
        material.f_mk, material.f_t0k, material.f_c0k, material.f_vk),
]
for key, value in sorted(overrides.items()):
    info.append("ueberschrieben: {} = {:g}".format(key, value))

for line in info:
    print(line)
