"""Tekton Info - status report of the environment.

First place to look when components turn red. Answers: which Python, which
compas_timber, is the structural branch there, is the repo found, is there a
worker venv.

This component is deliberately the only one that still prints something useful
*without* a working setup - it must never fail hard.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Info"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

report = []
ok = False


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


def _find_repo(explicit):
    """Look up the repo root: input > environment variable."""
    for candidate in _repo_candidates(explicit):
        candidate = str(candidate).strip() if candidate else ""
        if not candidate:
            continue
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(os.path.join(candidate, "packages")):
            return candidate
    return None


report.append("Python {}".format(sys.version.split()[0]))
if sys.version_info[:2] != (3, 9):
    report.append("  Note: Rhino 8 / CPython 3.9 was expected.")

# Installed from the Package Manager (and no repo named): nothing to find,
# the packages are importable as they are; only the worker needs a check.
installed = False
if not (repo and str(repo).strip()) and not os.environ.get("TEKTON_REPO"):
    import importlib.util

    installed = bool(importlib.util.find_spec("tekton_core") and importlib.util.find_spec("tekton_gh"))

root = None if installed else _find_repo(repo)
if installed:
    from tekton_gh import __version__ as _tekton_version
    from tekton_gh.worker import find_worker_python, worker_setup_hint

    report.append("Tekton {} (installed from the Package Manager, no repo needed)".format(_tekton_version))
    _worker = find_worker_python()
    if _worker:
        report.append("Worker: {}".format(_worker))
    else:
        report.append("Worker: NOT SET UP")
        report.extend("  " + line for line in worker_setup_hint().splitlines())
elif root is None:
    report.append("Repo: NOT FOUND")
    report.append("  -> Set the 'repo' input or the TEKTON_REPO environment variable.")
else:
    report.append("Repo: {}".format(root))
    # Deposit it for the session: most components have no repo input of
    # their own and would not find it otherwise.
    os.environ["TEKTON_REPO"] = root
    _remember_repo(root)

    # Make the layer that runs inside Rhino importable. tekton_dlubal and
    # tekton_saf are deliberately absent: they need grpc/pandas/vtk and Python
    # >= 3.10, so they only run in the worker process.
    fea_src = os.path.join(root, "packages", "tekton_core", "src")
    gh_src = os.path.join(root, "packages", "tekton_gh", "src")
    for path in (gh_src, fea_src):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    venv_python = os.path.join(root, ".venv", "bin", "python")
    if not os.path.isfile(venv_python):
        venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_python):
        report.append("Worker venv: OK")
    else:
        report.append("Worker venv: MISSING -> run 'uv sync --extra dev' in the repo.")

try:
    import compas

    report.append("compas {}".format(compas.__version__))
except ImportError as exc:
    report.append("compas missing ({})".format(exc))

try:
    import compas_timber

    report.append("compas_timber {}".format(compas_timber.__version__))
except ImportError as exc:
    compas_timber = None
    report.append("compas_timber missing ({})".format(exc))

if compas_timber is not None:
    try:
        import compas_timber.structural  # noqa: F401

        report.append("compas_timber.structural: OK")
        structural_ok = True
    except ImportError:
        structural_ok = False
        report.append("compas_timber.structural: MISSING")
        report.append(
            "  -> Wrong compas_timber version. Tekton needs the pinned revision "
            "of compas_timber main (newer than 3.0.2). In Rhino: create a "
            "dedicated venv with it (see packages/tekton_gh/README.md)."
        )

    if structural_ok:
        try:
            import tekton_core  # noqa: F401

            report.append("tekton_core: OK")
            ok = installed or root is not None
        except ImportError as exc:
            report.append("tekton_core not importable ({})".format(exc))

report.append("")
report.append("Backends (RFEM/SAF) do NOT run here but in the worker process:")
report.append("dlubal-api requires Python >= 3.10, Rhino runs 3.9.")

for line in report:
    print(line)
