"""Tekton Backend - bundle backend and connection data.

The API key does NOT belong in the GH file: that file gets mailed around,
lands in git, gets passed on. Leave it empty and set the environment variable
TEKTON_API_KEY instead - the worker reads it itself.

'repo' is the path to the monorepo; the venv with the backend packages
(Python >= 3.10) lives there.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Backend"  # type: ignore # noqa: F821


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
backend: str  # type: ignore
api_key: str  # type: ignore
repo: str  # type: ignore
filepath: str  # type: ignore

# --------------------- SCRIPT ---------------------

VALID = ("rfem", "rstab", "saf")
kind = (backend or "rfem").lower()
if kind not in VALID:
    _warn("Unknown backend '{}'. Allowed: {}.".format(kind, ", ".join(VALID)))
    kind = "rfem"

root = None
for candidate in (repo, os.environ.get("TEKTON_REPO")):
    if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
        root = os.path.expanduser(candidate)
        break

if root is None:
    _warn("Repo not found - TektonRun will fail. See TektonInfo.")
else:
    # Deposit it for the remaining components (most have no repo input of
    # their own).
    os.environ["TEKTON_REPO"] = root
    venv = os.path.join(root, ".venv", "bin", "python")
    if not os.path.isfile(venv):
        venv = os.path.join(root, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(venv):
        _warn("No .venv in the repo. Run 'uv sync --extra dev'.")

if api_key:
    _warn("API key on the canvas. Do not pass this GH file on - better to set TEKTON_API_KEY.")

class BackendConfig(object):
    """Backend settings as a single value.

    Deliberately a small class and not a dict: Grasshopper iterates a dict on
    output and then passes on only its *keys* - TektonRun would get four
    strings instead of one configuration. An object passes through GH as a
    single item.
    """

    def __init__(self, backend, repo, api_key, filepath):
        self.backend = backend
        self.repo = repo
        self.api_key = api_key
        self.filepath = filepath

    def __repr__(self):
        return "Backend({}, repo={})".format(self.backend, self.repo)


backend = BackendConfig(kind, root, api_key or None, filepath or None)

print("Backend: {}".format(kind))
print("Repo: {}".format(root or "NOT FOUND"))
print("API key: {}".format("from canvas" if api_key else "from environment (TEKTON_API_KEY)"))
if kind == "saf" and not filepath:
    _warn("Backend 'saf' needs a filepath.")
