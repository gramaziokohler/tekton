"""Grasshopper runtime layer for Tekton.

Runs **in-process in Rhino 8 (CPython 3.9)**. So unlike the rest of the
monorepo, Python 3.9 syntax applies here: no PEP 604 unions (``int | None``),
no ``match``, no ``slots=`` dataclasses.

What belongs here: anything more than one component needs - path setup, the
backend worker call, COMPAS <-> Rhino conversions. What does *not* belong
here: domain logic. That lives in ``compas_timber_fea``; this package is
wiring.
"""

from .env import ensure_tekton_path, remember_repo_root, tekton_repo_root, diagnose
from .rhino_io import (
    attach_value_list,
    document_units,
    line_to_rhino,
    point_to_rhino_pt,
    colour_ramp,
)
from .worker import WorkerError, run_backend

__all__ = [
    "ensure_tekton_path",
    "remember_repo_root",
    "tekton_repo_root",
    "diagnose",
    "attach_value_list",
    "document_units",
    "line_to_rhino",
    "point_to_rhino_pt",
    "colour_ramp",
    "run_backend",
    "WorkerError",
]

__version__ = "0.1.0"
