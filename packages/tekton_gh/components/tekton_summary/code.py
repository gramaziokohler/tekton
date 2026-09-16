"""Tekton Summary - the one page that says how a run went.

Deformations, reactions with an equilibrium check, extreme section forces,
and utilisation computed here in the neutral layer (EC5, WP1b) rather than
read from a backend add-on - so it also works with `backend = opensees`,
offline, without a licence.

Two rules it keeps, because breaking either makes a report worse than none:
every design number names the k_mod, gamma_M and service class it used, and
anything not verified says so. Buckling and lateral-torsional buckling are
NOT verified - the neutral model carries no buckling length (WP1c). A member
that passes here may still fail on stability.

Utilisation needs a material with strength values; grades from the preset
library have them. `report` is the text, `csv` one row per member, and the
headline numbers come out separately so they stay usable downstream.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Summary"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable. See TektonInfo when this fails."""
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
service_class: int  # type: ignore
duration: str  # type: ignore
gamma_M: float  # type: ignore
path: str  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'duration' as soon as the component lands on the canvas.
try:
    _setup()
    from tekton_gh.rhino_io import attach_value_list

    attach_value_list(  # type: ignore # noqa: F821
        ghenv,
        ["permanent", "long-term", "medium-term", "short-term", "instantaneous"],
        param_index=2,
        nickname="Duration",
    )
except Exception:
    pass

report = ""
csv = ""
max_displacement = None
max_utilization = None
worst_member = None
ok = False

if structural is None:
    report = "No model. Wire a StructuralModel with results into 'structural'."
else:
    try:
        _setup()

        from compas_timber_fea.design import DesignAssumptions
        from compas_timber_fea.design.checks import check_model
        from tekton_gh.summary import build_csv
        from tekton_gh.summary import build_report
        from tekton_gh.summary import headline_numbers

        model = structural
        if hasattr(model, "to_jsonstring") is False and isinstance(model, str):
            from compas_timber_fea.core.model import StructuralModel

            model = StructuralModel.from_json(model)

        if not getattr(model, "results", None):
            report = (
                "The model carries no results - run Tekton Run first.\n"
                "Summary reports what came back from a calculation; without\n"
                "results there is nothing to summarise."
            )
            _warn("No results on this model.")
        else:
            assumptions = DesignAssumptions(
                service_class=int(service_class) if service_class else 1,
                load_duration=duration or None,
                gamma_M=float(gamma_M) if gamma_M else None,
            )

            checks = None
            try:
                checks = check_model(model, assumptions)
            except Exception as error:  # noqa: BLE001 - a failed check must not kill the report
                _warn("Design checks skipped: {}".format(error))

            report = build_report(model, checks, assumptions)
            csv = build_csv(checks) if checks else ""

            numbers = headline_numbers(model, checks)
            max_displacement = numbers["max_displacement"]
            max_utilization = numbers["max_utilization"]
            worst_member = numbers["max_utilization_member"]

            if numbers["members_over_1"]:
                _warn(
                    "{} member(s) above utilisation 1.0 - see the report.".format(
                        numbers["members_over_1"]
                    )
                )

            if path:
                target = os.path.expanduser(str(path).strip())
                if target:
                    base, extension = os.path.splitext(target)
                    if not extension:
                        target = base + ".txt"
                    directory = os.path.dirname(target)
                    if directory and not os.path.isdir(directory):
                        os.makedirs(directory)
                    with open(target, "w") as handle:
                        handle.write(report)
                    if csv:
                        with open(base + ".csv", "w") as handle:
                            handle.write(csv)

            ok = True

    except Exception as error:  # noqa: BLE001
        report = "Summary failed: {}".format(error)
        _warn(str(error))

a = report
