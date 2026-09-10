"""Tekton Material Library - pick a grade instead of typing it.

On the first solve it attaches a value list to the `grade` input itself,
filled from `compas_timber_fea.core.materials.PRESETS`. That makes the library
the source of the choice: add a preset and it shows up in the menu, with
nothing to update here.

Without a selection the component lists what is available - it is then a
reference, not an error message.

Overriding single properties is **TektonMaterial**'s job; this one is the
quick reach into the shelf.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Material Library"  # type: ignore # noqa: F821


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


# --------------------- INPUTS ---------------------
grade: str  # type: ignore

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.materials import PRESETS, Material  # noqa: E402

from tekton_gh.rhino_io import attach_value_list  # noqa: E402

grades = sorted(PRESETS)

# Schedule the menu on the first solve. It comes into being after this solve;
# the next solve it triggers then runs through with a grade selected.
attach_value_list(ghenv, grades, param_index=0, nickname="Grade")  # type: ignore # noqa: F821

material = None
properties = []

name = (grade or "").strip().strip('"')
if not name:
    properties = ["{} grades available:".format(len(grades))]
    for key in grades:
        preset = PRESETS[key]
        properties.append("  {:<7} E0 {:>6.0f} N/mm2   rho {:>3.0f} kg/m3   {}".format(
            key, preset.E0_mean, preset.density_mean, preset.standard))
    properties.append("")
    properties.append("Select a grade to output a material.")
else:
    material = Material.resolve(name)
    if material.is_assumed:
        import Grasshopper

        ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            "Unknown grade '{}'. Properties borrowed from C24 and marked as "
            "an assumption.".format(name),
        )
    properties = [
        "{} ({})".format(material.name, material.standard),
        "E0,mean   {:>7.0f} N/mm2".format(material.E0_mean),
        "E0,k      {:>7.0f} N/mm2".format(material.E0_k),
        "E90,mean  {:>7.0f} N/mm2".format(material.E90_mean),
        "G,mean    {:>7.0f} N/mm2".format(material.G_mean),
        "rho,mean  {:>7.0f} kg/m3".format(material.density_mean),
        "rho,k     {:>7.0f} kg/m3".format(material.density_k),
        "f_m,k     {:>7.1f} N/mm2".format(material.f_mk),
        "f_t0,k    {:>7.1f} N/mm2".format(material.f_t0k),
        "f_c0,k    {:>7.1f} N/mm2".format(material.f_c0k),
        "f_v,k     {:>7.1f} N/mm2".format(material.f_vk),
    ]

for line in properties:
    print(line)
