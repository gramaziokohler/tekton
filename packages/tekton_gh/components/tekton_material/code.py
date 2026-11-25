"""Tekton Material - material from the library, with overrides.

A grade name is a key, not a material. RFEM does resolve names against its own
library, but SAF wants the numbers in the sheet, and OpenSees/Abaqus have no
library at all. So the neutral model carries the physical properties, and this
component supplies them.

The presets come from `tekton_core.core.materials` (EN 338 for solid
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
    """Make tekton_core importable."""
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and tekton_core, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("tekton_core") and importlib.util.find_spec("tekton_gh"):
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
    for package in ("tekton_gh", "tekton_core"):
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
elements = elements  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

_setup()
from tekton_core.core.materials import PRESETS, Material  # noqa: E402

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

# Assign the grade to elements, when any are wired in. The grade travels on
# the element, so the translator can give a C24 joist and a GL24h beam their
# own material and their own section - see WP7. Without elements the
# component is what it always was: a material definition.
assigned = 0
if elements:
    for element in elements:
        attributes = getattr(element, "attributes", None)
        if attributes is None:
            _warn("Skipped an object with no attributes - wire in beams or plates.")
            continue
        attributes["material"] = material.name
        assigned += 1
    info.append("assigned to {} element(s)".format(assigned))
    if material.is_assumed:
        info.append("careful: the properties are assumed, not from a standard")

for line in info:
    print(line)
