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


def _repo_candidates(explicit):
    """Where to look for the monorepo, cheapest and most certain first.

    Only `isdir` calls - never a filesystem search, this runs on every solve.
    The document guess is what makes a definition stored inside the repo work
    with nothing configured at all; the cache file is what makes the path
    survive a Rhino restart. Mirrors tekton_gh.env.discover_repo_root, which
    cannot be imported yet - finding the repo is what makes it importable.
    """
    yield explicit
    yield os.environ.get("TEKTON_REPO")
    try:
        document = ghenv.Component.OnPingDocument()  # type: ignore # noqa: F821
        current = os.path.dirname(document.FilePath) if document and document.FilePath else None
        for _ in range(8):
            if not current:
                break
            yield current
            parent = os.path.dirname(current)
            current = None if parent == current else parent
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.expanduser("~"), ".tekton", "repo-root")) as handle:
            yield handle.read()
    except Exception:
        pass
    for guess in ("~/Documents/GitHub/tekton", "~/Documents/git/tekton", "~/git/tekton",
                  "~/GitHub/tekton", "~/Developer/tekton", "~/src/tekton", "~/tekton",
                  "~/Documents/tekton", "~/Desktop/tekton"):
        yield guess


def _remember_repo(root):
    """Write the root down so the next Rhino session finds it by itself."""
    try:
        directory = os.path.join(os.path.expanduser("~"), ".tekton")
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, "repo-root"), "w") as handle:
            handle.write(root)
    except Exception:
        pass


def _setup(explicit_repo=None):
    """Make compas_timber_fea importable."""
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and compas_timber_fea, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("compas_timber_fea") and importlib.util.find_spec("tekton_gh"):
            return None
    root = None
    for candidate in _repo_candidates(explicit_repo):
        candidate = str(candidate).strip() if candidate else ""
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own, and
    # for the next Rhino session.
    os.environ["TEKTON_REPO"] = root
    _remember_repo(root)
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

from tekton_gh.rhino_io import attach_value_list, value_list_items  # noqa: E402

grades = sorted(PRESETS)

# Place the component, the menu is there - see attach_value_list for the
# guards that make this safe.
attach_value_list(ghenv, grades, param_index=0, nickname="Grade")  # type: ignore # noqa: F821
hint = value_list_items(ghenv, grades)  # type: ignore # noqa: F821

material = None
properties = []

name = (grade or "").strip().strip('"')
if not name:
    properties = list(hint)
    properties.append("{} grades available:".format(len(grades)))
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
