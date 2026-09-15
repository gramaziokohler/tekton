"""Tekton Attach Results - results back onto the timber model.

Writes `beam.attributes['analysis']` with, per load case, sample points (t
along the physical beam axis, N/Vy/Vz/Mt/My/Mz and displacement) and an
envelope, plus provenance. The work is done by
`compas_timber_fea.results.attach_results_to_timber`, offline-tested; this
script only picks the load case and reports.

Provenance is mandatory, not decoration: a number without 'which model state,
which combination, when' is a liability question. The worst failure mode is
results silently surviving a design change.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Attach"  # type: ignore # noqa: F821


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
model = model  # type: ignore # noqa: F821
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore

# --------------------- SCRIPT ---------------------

attached = 0

if model is None or structural is None:
    _warn("model and structural are both needed.")
else:
    _setup()
    from compas_timber_fea.results import ANALYSIS_KEY, attach_results_to_timber

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("No results in the model - run TektonRun first.")
    else:
        # None: every load case the results carry. A number: just that one.
        selected = results
        if load_case:
            case_id = int(load_case)
            if case_id in results:
                selected = {case_id: results[case_id]}
            else:
                _warn("Load case {} does not exist. Available: {}.".format(case_id, sorted(results)))
                selected = {}

        written = attach_results_to_timber(structural, model, result_sets=selected) if selected else {}
        attached = len(written)

        beams = list(model.beams)
        print("Results attached to {} of {} elements (load cases {}).".format(attached, len(beams), sorted(selected)))
        if written:
            sample = next(iter(written.values()))
            case = next(iter(sample["load_cases"].values()))
            print("Per beam: {} samples, envelope keys {}.".format(len(case["samples"]), sorted(case["envelope"])))
            print("Stored under beam.attributes['{}'].".format(ANALYSIS_KEY))
        if attached == 0 and selected:
            _warn(
                "No element matched. Usually the element GUIDs no longer "
                "line up - the timber model was changed after calculating."
            )
