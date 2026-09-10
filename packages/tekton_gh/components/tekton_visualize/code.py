"""Tekton Visualize - colour by result value.

Values above the upper bound go hard red instead of interpolating further: an
exceedance should catch the eye, not fade out gently.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Visualize"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
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
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
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
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore
quantity: str  # type: ignore
low: float  # type: ignore
high: float  # type: ignore

# --------------------- SCRIPT ---------------------

geometry = []
colours = []
legend = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    from tekton_gh.rhino_io import colour_ramp, document_units, member_lines

    units = getattr(structural, "source_units", "m")
    scale = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(units, 1.0)
    geometry = member_lines(structural, scale=scale)

    results = getattr(structural, "results", {}) or {}
    lo = 0.0 if low is None else float(low)
    hi = 1.0 if high is None else float(high)

    if not results:
        _warn("No results - everything is coloured neutrally.")
        colours = [colour_ramp(0.0, lo, hi) for _ in geometry]
        legend = ["no results"]
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)
        attribute = {"displacement": "displacement", "N": "axial", "My": "moment_y",
                     "Vz": "shear_z"}.get(quantity or "displacement", "displacement")

        values = []
        for member in structural.members:
            rows = (result_set.member_results or {}).get(member.id) if result_set else None
            if rows:
                values.append(max(abs(getattr(row, attribute, 0.0) or 0.0) for row in rows))
            else:
                values.append(0.0)

        colours = [colour_ramp(value, lo, hi) for value in values]
        legend = [
            "Quantity: {}".format(quantity or "displacement"),
            "Load case: {}".format(case_id),
            "Scale: {:.3g} .. {:.3g}".format(lo, hi),
            "Maximum in the model: {:.4g}".format(max(values) if values else 0.0),
        ]
        if values and max(values) > hi:
            _warn("Maximum value {:.4g} is above the scale upper bound {:.4g}.".format(max(values), hi))

for line in legend:
    print(line)
