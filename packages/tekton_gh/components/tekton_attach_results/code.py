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
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
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
    from compas_timber_fea.results import attach_plate_results_to_timber

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

        # Plates carry their own results: samples as points, not as a
        # parameter, because a plate has no axis to run along (WP5b).
        plate_checks = None
        try:
            from compas_timber_fea.design import DesignAssumptions
            from compas_timber_fea.design.plates import check_plates

            plate_checks = check_plates(structural, DesignAssumptions())
        except Exception as error:  # noqa: BLE001 - utilisation is a bonus, forces are not
            _warn("Plate utilisation skipped: {}".format(error))

        plates_written = attach_plate_results_to_timber(
            structural, model, result_sets=selected, plate_checks=plate_checks) if selected else {}

        beams = list(model.beams)
        plates = list(getattr(model, "plates", []) or [])
        print("Results attached to {} of {} beams (load cases {}).".format(attached, len(beams), sorted(selected)))
        if plates:
            print("Results attached to {} of {} plates.".format(len(plates_written), len(plates)))
        attached += len(plates_written)
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
