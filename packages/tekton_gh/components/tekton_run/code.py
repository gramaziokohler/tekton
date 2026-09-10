"""Tekton Run — Modell ans Backend, rechnen, Ergebnisse zurück.

Läuft in einem **eigenen Prozess**: `dlubal-api` verlangt Python >= 3.10 und
zieht grpcio/pandas/vtk mit, Rhino fährt 3.9. Die Prozessgrenze ist die
JSON-Serialisierung des neutralen Modells — kein eigenes Protokoll, und jeder
Lauf hinterlässt nebenbei ein übergabefähiges Modell.

NUR per Button auslösen. Zwei Gründe: der Lauf blockiert Grasshopper, solange
gerechnet wird, und jeder Lauf baut das Modell im Backend neu auf. Ein
Auto-Recompute bei jedem Slider-Wackeln wäre fatal.
"""
# venv: tekton
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

# Ergebnisse ueberleben einen Solve ohne Button: sonst waere jedes
# Canvas-Update ein Datenverlust. sticky haelt sie an der Komponenteninstanz.
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
        _warn("Zwischengespeichertes Ergebnis von {}. Button druecken fuer neuen Lauf.".format(_cached["stamp"]))
    else:
        log = ["Bereit. 'run' auf True setzen, um zu rechnen."]

elif structural is None or backend is None:
    _error("structural und backend werden beide gebraucht.")

else:
    repo = backend.get("repo") if isinstance(backend, dict) else getattr(backend, "repo", None)
    kind = backend.get("backend") if isinstance(backend, dict) else getattr(backend, "backend", "rfem")
    api_key = backend.get("api_key") if isinstance(backend, dict) else getattr(backend, "api_key", None)

    gh_src = os.path.join(repo or "", "packages", "tekton_gh", "src")
    if os.path.isdir(gh_src) and gh_src not in sys.path:
        sys.path.insert(0, gh_src)

    from tekton_gh.worker import WorkerError, model_fingerprint, run_backend

    fingerprint = model_fingerprint(structural)
    started = time.time()
    ghenv.Component.Message = "rechnet..."  # type: ignore # noqa: F821

    try:
        result_model, worker_log = run_backend(
            structural,
            repo_root=repo,
            backend=kind or "rfem",
            load_cases=list(load_cases) if load_cases else None,
            model_name=model_name or "tekton-gh",
            api_key=api_key,
            calculate=True if calculate is None else bool(calculate),
        )
    except WorkerError as exc:
        _error(str(exc))
        log = str(exc).splitlines()
        ghenv.Component.Message = "Fehler"  # type: ignore # noqa: F821
    else:
        elapsed = time.time() - started
        log = list(worker_log) + ["Dauer: {:.1f}s".format(elapsed)]

        if result_model is not None:
            structural = result_model
            # Fingerprint des *gesendeten* Modells in jeden Ergebnissatz
            # schreiben. Damit kann TektonResults spaeter vergleichen, ob der
            # Canvas inzwischen ein anderes Modell zeigt als das gerechnete —
            # Ergebnisse, die still eine Entwurfsaenderung ueberleben, sind der
            # gefaehrlichste Fehlermodus dieses Workflows.
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
                "Berechnung ausgeloest, aber keine Ergebnisse zurueckgekommen. "
                "Das Worker-Protokoll unten nennt den Grund — meist eine "
                "Ergebnistabelle, die RFEM nicht liefert."
            )

for line in log:
    print(line)
