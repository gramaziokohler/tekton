"""Calling the backend worker from inside Rhino.

Why a second process at all: `dlubal-api` requires Python >= 3.10 and pulls in
grpcio, pandas and vtk. Rhino 8 runs CPython 3.9. The RFEM client therefore
cannot run in-process on principle - regardless of how we write our own code.

The process boundary is the JSON serialisation of the neutral model
(`StructuralModel.to_json` / `.from_json`). No protocol of our own, and every
run leaves behind a diffable model as a side effect - the same artefact that
is handed over to engineers.

Flow::

    Rhino                          Worker (repo venv, Py 3.12)
    -----                          --------------------------
    model.to_json(in.json)   -->   from_json, push, calculate, read
    from_json(out.json)      <--   model.results filled, to_json

TODO(scaffold): The worker CLI (`tekton run ...`) does not exist yet. It
belongs in `tekton_app`, which already depends on compas_dlubal and compas_saf
anyway. Until then `run_backend` raises a WorkerError with instructions for
doing the same step by hand.
"""

import json
import os
import subprocess
import sys
import tempfile


class WorkerError(RuntimeError):
    """The worker did not run, or it ran and was unhappy."""


def worker_python(repo_root):
    """Find the interpreter of the repo venv.

    Rhino's own interpreter will not do - it is 3.9 and has no grpc.
    """
    candidates = [
        os.path.join(repo_root, ".venv", "bin", "python"),
        os.path.join(repo_root, ".venv", "Scripts", "python.exe"),  # Windows
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise WorkerError(
        "No venv found in the repo ({}). Expected: .venv in the repo root - "
        "run 'uv sync --extra dev' in the repo.".format(repo_root)
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
    design=False,
):
    """Send the model to a backend and (for RFEM) fetch results back.

    Parameters
    ----------
    structural_model : compas_timber_fea.core.model.StructuralModel
    repo_root : str
        Root of the monorepo; the venv with the backend packages lives there.
    backend : {'rfem', 'rstab', 'saf', 'opensees'}
    load_cases : list of int, optional
        Load cases whose results are read. None = all.
    api_key : str, optional
        Never write this into the GH file - that file gets mailed around.
        Better: an environment variable the worker reads itself.
    output_path : str, optional
        Where the result model is written. None = temporary.
    calculate : bool
        When False, only push, do not calculate (the handoff case).
    design : bool
        rfem only: set up the timber design add-on and read its ratios.

    Returns
    -------
    tuple
        ``(model_with_results, log_lines)`` - the *newly loaded* model, not
        the one passed in. The results come back out of the worker process.

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
    if design:
        command.append("--design")
    # Every run rebuilds the backend model from scratch - that is the contract
    # the Run component documents. Without this, the second push into the same
    # RFEM model fails on "Material No. 1 already exists".
    if backend in ("rfem", "rstab"):
        command.append("--delete-all")

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
        raise WorkerError("Worker could not be started: {}".format(exc))
    except subprocess.TimeoutExpired:
        raise WorkerError(
            "Worker timed out after {}s. RFEM is still calculating, or a modal "
            "dialog is waiting for confirmation.".format(timeout)
        )

    output = completed.stdout.decode("utf-8", "replace") if completed.stdout else ""
    log_lines = [line for line in output.splitlines() if line.strip()]

    if completed.returncode != 0:
        raise WorkerError(
            "Worker exited with code {}.\n{}".format(completed.returncode, output[-2000:])
        )

    if backend == "saf":
        return None, log_lines

    if not os.path.isfile(out_path):
        raise WorkerError("Worker reported success but wrote no result to {}".format(out_path))

    from compas_timber_fea.core.model import StructuralModel

    return StructuralModel.from_json(out_path), log_lines


def model_fingerprint(structural_model):
    """Short hash over the structurally relevant model data.

    What for: Grasshopper holds on to old outputs. Results on the canvas can
    describe a model that changed long ago - the most dangerous failure mode
    of this workflow (see ``discussion/roundtrip.md``). The fingerprint is
    written alongside every calculation and checked by the result components
    against the current model: if it differs, they warn 'results stale'.

    TODO(scaffold): Should move into the neutral layer once the provenance
    structure from roundtrip.md exists - this is only the GH-side placeholder,
    so the components already have the right shape.
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
    """One-liner for error messages that names the most common cause."""
    return "Rhino Python: {}. Backends need >= 3.10 and therefore run in the worker.".format(
        sys.version.split()[0]
    )
