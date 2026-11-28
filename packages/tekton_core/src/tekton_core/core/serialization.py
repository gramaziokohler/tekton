"""JSON serialisation for the neutral StructuralModel.

The model is the artefact that outlives a single session: it is what gets
handed to an engineer, diffed between design iterations, and used to map
analysis results back onto source elements. That requires it to survive a
round-trip to disk, including COMPAS geometry and infinite stiffness values.

Dataclasses are converted field by field rather than with ``dataclasses.asdict``
so that geometry, nested dataclasses and non-finite floats stay reversible.
"""

import json
import math
from dataclasses import fields
from dataclasses import is_dataclass

from compas.geometry import Point
from compas.geometry import Vector

from tekton_core.core import materials as materials_module
from tekton_core.core import model as model_module
from tekton_core.core import releases as releases_module

#: Sentinels for values JSON cannot express natively.
_INFINITY = "Infinity"
_NEG_INFINITY = "-Infinity"

FORMAT_VERSION = 1


def _encode(value):
    if isinstance(value, Point):
        return {"__type__": "Point", "value": [value.x, value.y, value.z]}
    if isinstance(value, Vector):
        return {"__type__": "Vector", "value": [value.x, value.y, value.z]}
    if is_dataclass(value):
        return {
            "__type__": type(value).__name__,
            "value": {f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, float):
        if value == math.inf:
            return _INFINITY
        if value == -math.inf:
            return _NEG_INFINITY
        return value
    if isinstance(value, dict):
        # Keys are ints in several places (materials, results); JSON forces
        # strings, so the key type is recorded to restore it on load.
        return {"__dict__": [[_encode(k), _encode(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _dataclass_types():
    """All dataclasses that may appear in a serialised model, by name."""
    types = {}
    for module in (model_module, releases_module, materials_module):
        for name in dir(module):
            candidate = getattr(module, name)
            if isinstance(candidate, type) and is_dataclass(candidate):
                types[name] = candidate
    return types


def _decode(value, types):
    if isinstance(value, str):
        if value == _INFINITY:
            return math.inf
        if value == _NEG_INFINITY:
            return -math.inf
        return value
    if isinstance(value, list):
        return [_decode(item, types) for item in value]
    if isinstance(value, dict):
        if "__dict__" in value:
            return {_decode(k, types): _decode(v, types) for k, v in value["__dict__"]}
        type_name = value.get("__type__")
        if type_name == "Point":
            return Point(*value["value"])
        if type_name == "Vector":
            return Vector(*value["value"])
        if type_name in types:
            cls = types[type_name]
            kwargs = {k: _decode(v, types) for k, v in value["value"].items()}
            return cls(**kwargs)
        if type_name is not None:
            raise ValueError(f"Unknown type in serialised model: {type_name!r}")
        return {k: _decode(v, types) for k, v in value.items()}
    return value


def model_to_data(structural_model):
    """Return a JSON-compatible dict describing the model."""
    return {
        "format_version": FORMAT_VERSION,
        "model": _encode(structural_model),
    }


def model_from_data(data):
    """Rebuild a model from the dict produced by :func:`model_to_data`."""
    version = data.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(f"Unsupported model format version: {version!r} (expected {FORMAT_VERSION})")
    return _decode(data["model"], _dataclass_types())


def model_to_json(structural_model, filepath, pretty=True):
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(model_to_data(structural_model), handle, indent=2 if pretty else None)
    return filepath


def model_from_json(filepath):
    with open(filepath, encoding="utf-8") as handle:
        return model_from_data(json.load(handle))
