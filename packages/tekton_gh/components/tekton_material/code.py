"""Tekton Material - material from the library, with overrides.

A grade name is a key, not a material. RFEM does resolve names against its own
library, but SAF wants the numbers in the sheet, and OpenSees/Abaqus have no
library at all. So the neutral model carries the physical properties, and this
component supplies them.

The presets come from `compas_timber_fea.core.materials` (EN 338 for solid
timber, EN 14080 for glulam) - one source for GH, GUI and CLI.

Overrides are the normal case for tested material: preset as a starting point,
single values replaced. They travel with the model and appear in the
assumptions report.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Material"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea importable."""
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
    # Unknown grade: the properties are borrowed but visibly marked as an
    # assumption - a named assumption beats a silent one.
    material = Material.resolve(name)
    if overrides:
        from dataclasses import replace

        material = replace(material, **overrides)
    _warn(
        "Unknown grade '{}'. Properties borrowed from C24 and marked as an "
        "assumption. Known: {}.".format(name, ", ".join(sorted(PRESETS)))
    )

info = [
    "{} ({})".format(material.name, material.standard),
    "E0,mean {:.0f} N/mm2 | E90,mean {:.0f} | G {:.0f}".format(
        material.E0_mean, material.E90_mean, material.G_mean),
    "Density {:.0f} kg/m3 (characteristic {:.0f})".format(
        material.density_mean, material.density_k),
    "f_m,k {:.1f} | f_t0,k {:.1f} | f_c0,k {:.1f} | f_v,k {:.1f} N/mm2".format(
        material.f_mk, material.f_t0k, material.f_c0k, material.f_vk),
]
for key, value in sorted(overrides.items()):
    info.append("overridden: {} = {:g}".format(key, value))

for line in info:
    print(line)
