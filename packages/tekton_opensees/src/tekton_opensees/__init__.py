"""OpenSees backend: the neutral StructuralModel solved with openseespy.

Beams first. Everything the adapter emits was proven in
``tests/spike_opensees.py`` against closed-form solutions.
"""

from tekton_opensees.runner import OpenSeesRunner  # noqa: F401
from tekton_opensees.runner import run_model  # noqa: F401

__all__ = ["OpenSeesRunner", "run_model"]
