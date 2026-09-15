"""Tekton Run - model to the backend, calculate, results back.

Runs in a **process of its own**: `dlubal-api` requires Python >= 3.10 and
pulls in grpcio/pandas/vtk, Rhino runs 3.9. The process boundary is the JSON
serialisation of the neutral model - no protocol of our own, and every run
leaves behind a handover-ready model as a side effect.

Trigger by button ONLY. Two reasons: the run blocks Grasshopper for as long as
it calculates, and every run rebuilds the model in the backend from scratch. An
auto-recompute on every slider wiggle would be fatal.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys
import time

ghenv.Component.Message = "Run"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
backend = backend  # type: ignore # noqa: F821
load_cases = load_cases  # type: ignore # noqa: F821
model_name: str  # type: ignore
calculate: bool  # type: ignore
run: bool  # type: ignore

# --------------------- SCRIPT ---------------------

log = []
stamp = None

# Results survive a solve without the button: otherwise every canvas update
# would lose data. sticky keeps them on the component instance.
import scriptcontext as sc  # noqa: E402

_key = "tekton_run_{}".format(ghenv.Component.InstanceGuid)  # type: ignore # noqa: F821
_cached = sc.sticky.get(_key)


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )


def _error(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message
    )


if not run:
    if _cached:
        structural, log, stamp = _cached["model"], _cached["log"], _cached["stamp"]
        ghenv.Component.Message = "Run\n({})".format(_cached["stamp"])  # type: ignore # noqa: F821
        _warn("Cached result from {}. Press the button for a new run.".format(_cached["stamp"]))
    else:
        log = ["Ready. Set 'run' to True to calculate."]

elif structural is None or backend is None:
    _error("structural and backend are both needed.")

else:
    def _cfg(key, default=None):
        if isinstance(backend, dict):
            return backend.get(key, default)
        return getattr(backend, key, default)

    repo = _cfg("repo")
    kind = _cfg("backend", "rfem")
    api_key = _cfg("api_key")
    filepath = _cfg("filepath")

    gh_src = os.path.join(repo or "", "packages", "tekton_gh", "src")
    if os.path.isdir(gh_src) and gh_src not in sys.path:
        sys.path.insert(0, gh_src)

    # Rhino keeps imported modules for the life of the process. Reload on
    # every run, so an edit to tekton_gh/worker.py in the repo takes effect
    # without restarting Rhino. Cheap: this only runs behind the button.
    import importlib
    import tekton_gh.worker
    importlib.reload(tekton_gh.worker)
    from tekton_gh.worker import WorkerError, model_fingerprint, run_backend

    fingerprint = model_fingerprint(structural)
    started = time.time()
    ghenv.Component.Message = "calculating..."  # type: ignore # noqa: F821

    try:
        result_model, worker_log = run_backend(
            structural,
            repo_root=repo,
            backend=kind or "rfem",
            load_cases=list(load_cases) if load_cases else None,
            model_name=model_name or "tekton-gh",
            api_key=api_key,
            calculate=True if calculate is None else bool(calculate),
            # Without the path a SAF export lands in the temp folder instead
            # of where TektonBackend wanted it put.
            output_path=filepath,
        )
    except WorkerError as exc:
        _error(str(exc))
        log = str(exc).splitlines()
        ghenv.Component.Message = "Error"  # type: ignore # noqa: F821
    else:
        elapsed = time.time() - started
        log = list(worker_log) + ["Duration: {:.1f}s".format(elapsed)]

        if result_model is not None:
            structural = result_model
            # Write the fingerprint of the *sent* model into every result set.
            # That lets TektonResults compare later whether the canvas now shows
            # a different model than the one calculated - results that silently
            # survive a design change are the most dangerous failure mode of
            # this workflow.
            for result_set in (getattr(structural, "results", {}) or {}).values():
                metadata = getattr(result_set, "metadata", None)
                if metadata is None:
                    result_set.metadata = metadata = {}
                metadata["model_fingerprint"] = fingerprint
                metadata["calculated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        stamp = "{} @ {}".format(fingerprint, time.strftime("%H:%M:%S"))
        ghenv.Component.Message = "Run\n({})".format(stamp)  # type: ignore # noqa: F821
        sc.sticky[_key] = {"model": structural, "log": log, "stamp": stamp}

        total_results = len(getattr(structural, "results", {}) or {})
        if total_results == 0:
            _warn(
                "Calculation triggered, but no results came back. The worker "
                "log below names the reason - usually a result table that RFEM "
                "does not deliver."
            )

for line in log:
    print(line)
