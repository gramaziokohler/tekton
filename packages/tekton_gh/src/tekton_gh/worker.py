"""Aufruf des Backend-Workers aus Rhino heraus.

Warum überhaupt ein zweiter Prozess: `dlubal-api` verlangt Python >= 3.10 und
zieht grpcio, pandas und vtk mit. Rhino 8 fährt CPython 3.9. Der RFEM-Client
kann also prinzipiell nicht in-process laufen — unabhängig davon, wie wir
unseren eigenen Code schreiben.

Die Prozessgrenze ist die JSON-Serialisierung des neutralen Modells
(`StructuralModel.to_json` / `.from_json`). Kein eigenes Protokoll, und jeder
Lauf hinterlässt nebenbei ein diffbares Modell — dasselbe Artefakt, das an
Statiker übergeben wird.

Ablauf::

    Rhino                          Worker (repo-venv, Py 3.12)
    -----                          --------------------------
    model.to_json(in.json)   -->   from_json, push, calculate, read
    from_json(out.json)      <--   model.results gefüllt, to_json

TODO(scaffold): Der Worker-CLI (`tekton run ...`) existiert noch nicht.
Er gehört nach `tekton_app`, das compas_dlubal und compas_saf ohnehin schon
als Abhängigkeit hat. Bis dahin wirft `run_backend` eine WorkerError mit
einer Anleitung, wie man denselben Schritt von Hand ausführt.
"""

import json
import os
import subprocess
import sys
import tempfile


class WorkerError(RuntimeError):
    """Der Worker lief nicht, oder er lief und war unglücklich."""


def worker_python(repo_root):
    """Interpreter des Repo-venvs finden.

    Rhinos eigener Interpreter taugt nicht — der ist 3.9 und hat kein grpc.
    """
    candidates = [
        os.path.join(repo_root, ".venv", "bin", "python"),
        os.path.join(repo_root, ".venv", "Scripts", "python.exe"),  # Windows
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise WorkerError(
        "Kein venv im Repo gefunden ({}). Erwartet: .venv im Repo-Root — "
        "'uv sync --extra dev' im Repo ausfuehren.".format(repo_root)
    )


def run_backend(
    structural_model,
    repo_root,
    backend="rfem",
    load_cases=None,
    model_name="tekton-gh",
    api_key=None,
    output_path=None,
    calculate=True,
    timeout=600,
):
    """Modell an ein Backend schicken und (bei RFEM) Ergebnisse zurückholen.

    Parameters
    ----------
    structural_model : compas_timber_fea.core.model.StructuralModel
    repo_root : str
        Wurzel des Monorepos; dort liegt das venv mit den Backend-Paketen.
    backend : {'rfem', 'rstab', 'saf'}
    load_cases : list of int, optional
        Lastfälle, deren Ergebnisse gelesen werden. None = alle.
    api_key : str, optional
        Niemals in die GH-Datei schreiben — die wandert per Mail weiter.
        Besser: Umgebungsvariable, die der Worker selbst liest.
    output_path : str, optional
        Wohin das Ergebnismodell geschrieben wird. None = temporär.
    calculate : bool
        Bei False nur pushen, nicht rechnen (Handoff-Fall).

    Returns
    -------
    tuple
        ``(model_with_results, log_lines)`` — das *neu geladene* Modell, nicht
        das übergebene. Die Ergebnisse kommen aus dem Worker-Prozess zurück.

    Raises
    ------
    WorkerError
    """
    python = worker_python(repo_root)

    tmpdir = tempfile.mkdtemp(prefix="tekton_gh_")
    in_path = os.path.join(tmpdir, "model.json")
    out_path = output_path or os.path.join(tmpdir, "model.result.json")

    structural_model.to_json(in_path)

    command = [
        python,
        "-m",
        "tekton_app.worker",
        in_path,
        "--backend",
        backend,
        "--out",
        out_path,
        "--model-name",
        model_name,
    ]
    if load_cases:
        command += ["--load-cases", ",".join(str(int(lc)) for lc in load_cases)]
    if not calculate:
        command.append("--no-calculate")

    env = dict(os.environ)
    if api_key:
        env["TEKTON_API_KEY"] = api_key

    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except OSError as exc:
        raise WorkerError("Worker nicht startbar: {}".format(exc))
    except subprocess.TimeoutExpired:
        raise WorkerError(
            "Worker-Timeout nach {}s. RFEM rechnet noch, oder es wartet ein "
            "modaler Dialog auf Bestaetigung.".format(timeout)
        )

    output = completed.stdout.decode("utf-8", "replace") if completed.stdout else ""
    log_lines = [line for line in output.splitlines() if line.strip()]

    if completed.returncode != 0:
        raise WorkerError(
            "Worker beendet mit Code {}.\n{}".format(completed.returncode, output[-2000:])
        )

    if backend == "saf":
        return None, log_lines

    if not os.path.isfile(out_path):
        raise WorkerError("Worker meldete Erfolg, schrieb aber kein Ergebnis nach {}".format(out_path))

    from compas_timber_fea.core.model import StructuralModel

    return StructuralModel.from_json(out_path), log_lines


def model_fingerprint(structural_model):
    """Kurzer Hash über die statisch relevanten Modelldaten.

    Wozu: Grasshopper hält alte Outputs fest. Ergebnisse am Canvas können ein
    längst geändertes Modell beschreiben — der gefährlichste Failure-Mode
    dieses Workflows (siehe ``discussion/roundtrip.md``). Der Fingerprint wird
    beim Rechnen mitgeschrieben und von den Ergebnis-Komponenten gegen das
    aktuelle Modell geprüft: weicht er ab, warnen sie 'Ergebnisse veraltet'.

    TODO(scaffold): Sollte in die neutrale Schicht wandern, sobald die
    Provenance-Struktur aus roundtrip.md steht — hier ist nur der GH-nahe
    Platzhalter, damit die Komponenten schon die richtige Form haben.
    """
    import hashlib

    payload = {
        "nodes": [[n.id, list(n.point)] for n in structural_model.nodes],
        "members": [[m.id, m.node_start, m.node_end, m.section_id] for m in structural_model.members],
        "surfaces": [[s.id, list(s.nodes), s.thickness_id] for s in structural_model.surfaces],
        "supports": [[s.id, list(s.nodes)] for s in structural_model.supports],
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def python_version_note():
    """Einzeiler für Fehlermeldungen, der die häufigste Ursache nennt."""
    return "Rhino-Python: {}. Backends brauchen >= 3.10 und laufen daher im Worker.".format(
        sys.version.split()[0]
    )
