"""Tekton Backend - bundle backend and connection data.

The API key does NOT belong in the GH file: that file gets mailed around,
lands in git, gets passed on. Three ways to hand it over, in order of
preference:

1. Leave 'api_key' empty. The worker reads TEKTON_API_KEY or DLUBAL_API_KEY
   from the environment, or from the '.env' in the repo root.
2. Give 'api_key' the *path* to a file holding the key - a '.env' with
   'DLUBAL_API_KEY=...' or a text file containing nothing but the key. Only
   the path ends up in the GH file.
3. Paste the key itself. Works, but warns: it is now in the definition.

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
design: bool  # type: ignore
mesh_size: float  # type: ignore

# --------------------- SCRIPT ---------------------

VALID = ("rfem", "rstab", "saf", "opensees")
try:
    _gh_src = os.path.join(os.path.expanduser(repo or os.environ.get("TEKTON_REPO", "")), "packages", "tekton_gh", "src")
    if os.path.isdir(_gh_src) and _gh_src not in sys.path:
        sys.path.insert(0, _gh_src)
    from tekton_gh.rhino_io import attach_value_list
    attach_value_list(ghenv, list(VALID), param_index=0, nickname="Backend")  # type: ignore # noqa: F821
except Exception:
    pass  # no repo yet - the warning below says so; the menu is a convenience
kind = (backend or "rfem").lower().strip('"')
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

def _key_from_file(path):
    """Read the key from a '.env'-style file (KEY=VALUE) or a bare-key file.

    Returns None when the file has no usable line - the caller then treats the
    input as the key itself.
    """
    with open(path) as handle:
        lines = [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]
    for line in lines:
        if "=" in line:
            name, value = line.split("=", 1)
            if name.strip() in ("TEKTON_API_KEY", "DLUBAL_API_KEY"):
                return value.strip().strip("'\"") or None
    if len(lines) == 1 and "=" not in lines[0]:
        return lines[0]
    return None


key_source = "from environment (TEKTON_API_KEY / DLUBAL_API_KEY / repo .env)"
if api_key:
    candidate = os.path.expanduser(api_key.strip())
    if os.path.isfile(candidate):
        api_key = _key_from_file(candidate)
        if api_key:
            key_source = "from file {}".format(candidate)
        else:
            _warn("No key found in {} - expected DLUBAL_API_KEY=... or a single line.".format(candidate))
    else:
        key_source = "from canvas"
        _warn("API key on the canvas. Do not pass this GH file on - better a file path or TEKTON_API_KEY.")

class BackendConfig(object):
    """Backend settings as a single value.

    Deliberately a small class and not a dict: Grasshopper iterates a dict on
    output and then passes on only its *keys* - TektonRun would get four
    strings instead of one configuration. An object passes through GH as a
    single item.
    """

    def __init__(self, backend, repo, api_key, filepath, design=False, mesh_size=None):
        self.backend = backend
        self.repo = repo
        self.api_key = api_key
        self.filepath = filepath
        self.design = design
        self.mesh_size = mesh_size

    def __repr__(self):
        return "Backend({}, repo={})".format(self.backend, self.repo)


backend = BackendConfig(kind, root, api_key or None, filepath or None, bool(design),
                       float(mesh_size) if mesh_size else None)

print("Backend: {}".format(kind))
print("Repo: {}".format(root or "NOT FOUND"))
print("API key: {}".format(key_source))
if kind == "saf" and not filepath:
    _warn("Backend 'saf' needs a filepath.")
if kind == "opensees":
    print("OpenSees: beams and plates, no licence, no key, solves in milliseconds.")
    if mesh_size:
        print("Plate mesh: {} m target edge length.".format(mesh_size))
        if float(mesh_size) <= 0:
            _warn("'mesh_size' must be positive - ignored.")
    else:
        print("Plate mesh: 0.5 m target edge length (default). Smaller = finer and slower.")
elif mesh_size:
    _warn("'mesh_size' only applies to the opensees backend - ignored for '{}'.".format(kind))
if design:
    if kind != "rfem":
        _warn("'design' only works with the rfem backend - ignored for '{}'.".format(kind))
    else:
        print("Timber design: RFEM add-on on, utilisation read per station (see 'design' in the result metadata).")
