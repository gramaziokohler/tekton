"""Tekton Translate - TimberModel -> neutral StructuralModel.

Core of the bridge. Turns physical elements into a mechanical analysis model:
system lines, nodes, cross-sections, releases, supports.

The 'report' output is not debug output. It lists the idealisation assumptions
that were made - the thing the engineer will later argue about. Put it on the
canvas, do not throw it away.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Translate"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
model = model  # type: ignore # noqa: F821  TimberModel
material = material  # type: ignore # noqa: F821
joint_policy = joint_policy  # type: ignore # noqa: F821
plate_policy = plate_policy  # type: ignore # noqa: F821
load_cases = load_cases  # type: ignore # noqa: F821
units: str  # type: ignore
repo: str  # type: ignore

# --------------------- SETUP ---------------------


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


def _setup(explicit_repo):
    """Make compas_timber_fea importable.

    In Rhino the official COMPAS Timber plugin may already have loaded another
    version (1.0.5) which knows no `compas_timber.structural`. Hence purge +
    path priority, not just an append.
    """
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
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
    _remember_repo(root)

    for name in [m for m in list(sys.modules) if m.split(".")[0] in ("compas_timber", "compas_timber_fea", "tekton_gh")]:
        del sys.modules[name]

    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


# --------------------- SCRIPT ---------------------

structural = None
report = []
preview = []

if model is None:
    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        __import__("Grasshopper").Kernel.GH_RuntimeMessageLevel.Warning,
        "No TimberModel connected.",
    )
else:
    _setup(repo)

    from compas_timber_fea import TimberToStructural
    from compas_timber_fea.core.joint_policy import JointPolicy

    from tekton_gh.rhino_io import document_units, member_lines

    # Units: the model comes out of Rhino, so it is typically mm; the neutral
    # model works in metres. Without this translation a mm model silently turns
    # into a 200-metre plate.
    source_units = units or document_units(default="m")

    # TODO(scaffold): material is only a name string today, which RFEM
    # resolves against its own library. Once the Material dataclass with presets
    # exists, pass the object through here and write
    # the properties into the neutral model.
    material_name = material if isinstance(material, str) else (getattr(material, "name", None) or "C24")

    policy = joint_policy if joint_policy is not None else JointPolicy.conservative()

    translator = TimberToStructural(
        material_name=material_name,
        source_units=source_units,
        joint_policy=policy,
        plate_policy=plate_policy,
        load_cases=list(load_cases) if load_cases else None,
    )

    structural = translator.translate(model)
    report = list(translator.report)

    # Apply the span direction override from the plate policy. Only possible
    # here: before translating there are no surfaces. The direction decides how
    # plate results are to be read (RFEM's m_x follows the surface axes), and
    # later becomes SurfaceRegion.frame.x in the plate graph.
    override = getattr(plate_policy, "span_direction_override", None)
    if override and structural.surfaces:
        from compas.geometry import Vector

        for surface in structural.surfaces:
            surface.span_direction = Vector(*override)
        report.append(
            "Span direction of all {} surfaces set to ({:.3f}, {:.3f}, {:.3f}) "
            "(override from the plate policy).".format(len(structural.surfaces), *override)
        )

    report.insert(0, "Units of the timber model: {}".format(source_units))
    report.insert(1, "Material (global): {}".format(material_name))
    if joint_policy is None:
        report.insert(2, "Joints: conservative (pinned) - no policy connected.")

    # Preview in document units: the neutral model is in metres.
    scale = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(source_units, 1.0)
    preview = member_lines(structural, scale=scale)

    print("{} nodes, {} members, {} surfaces, {} supports".format(
        len(structural.nodes), len(structural.members),
        len(structural.surfaces), len(structural.supports)))

    if not structural.supports:
        import Grasshopper

        ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            "Model has no supports. Use TektonSupport - otherwise the backend "
            "calculates a floating system.",
        )
