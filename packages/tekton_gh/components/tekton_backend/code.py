"""Tekton Backend — Backend und Verbindungsdaten buendeln.

Der API-Key gehoert NICHT in die GH-Datei: die wandert per Mail weiter,
landet in Git, wird weitergegeben. Leer lassen und stattdessen die
Umgebungsvariable TEKTON_API_KEY setzen — der Worker liest sie selbst.

'repo' ist der Pfad zum Monorepo; dort liegt das venv mit den
Backend-Paketen (Python >= 3.10).
"""
# venv: tekton
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
    _warn("Unbekanntes Backend '{}'. Erlaubt: {}.".format(kind, ", ".join(VALID)))
    kind = "rfem"

root = None
for candidate in (repo, os.environ.get("TEKTON_REPO")):
    if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
        root = os.path.expanduser(candidate)
        break

if root is None:
    _warn("Repo nicht gefunden — TektonRun wird fehlschlagen. Siehe TektonInfo.")
else:
    venv = os.path.join(root, ".venv", "bin", "python")
    if not os.path.isfile(venv):
        venv = os.path.join(root, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(venv):
        _warn("Kein .venv im Repo. 'uv sync --extra dev' ausfuehren.")

if api_key:
    _warn("API-Key im Canvas. Diese GH-Datei nicht weitergeben — besser TEKTON_API_KEY setzen.")

backend = {
    "backend": kind,
    "repo": root,
    "api_key": api_key or None,
    "filepath": filepath or None,
}

print("Backend: {}".format(kind))
print("Repo: {}".format(root or "NICHT GEFUNDEN"))
print("API-Key: {}".format("aus Canvas" if api_key else "aus Umgebung (TEKTON_API_KEY)"))
if kind == "saf" and not filepath:
    _warn("Backend 'saf' braucht einen filepath.")
