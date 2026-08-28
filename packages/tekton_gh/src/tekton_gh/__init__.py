"""Grasshopper-Laufzeitschicht für Tekton.

Läuft **in-process in Rhino 8 (CPython 3.9)**. Darum gilt hier, anders als im
Rest des Monorepos, Python-3.9-Syntax: keine PEP-604-Unions (``int | None``),
kein ``match``, keine ``slots=``-Dataclasses.

Was hier hineingehört: alles, was mehr als eine Komponente braucht — Pfad-Setup,
der Aufruf des Backend-Workers, Konvertierungen COMPAS <-> Rhino. Was *nicht*
hineingehört: Fachlogik. Die lebt in ``compas_timber_fea``; dieses Paket ist
Verkabelung.
"""

from .env import ensure_tekton_path, tekton_repo_root, diagnose
from .rhino_io import (
    document_units,
    line_to_rhino,
    point_to_rhino_pt,
    colour_ramp,
)
from .worker import WorkerError, run_backend

__all__ = [
    "ensure_tekton_path",
    "tekton_repo_root",
    "diagnose",
    "document_units",
    "line_to_rhino",
    "point_to_rhino_pt",
    "colour_ramp",
    "run_backend",
    "WorkerError",
]

__version__ = "0.1.0"
