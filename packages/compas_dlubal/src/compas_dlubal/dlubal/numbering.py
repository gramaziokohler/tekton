"""Allocating RFEM's object numbers for a neutral model.

The neutral id is a hash over 2^31 - stable across edits, derived from the
source GUID, never set by a backend. RFEM's object number is the opposite:
small, dense, and RFEM's own property. Dlubal document 999,999 objects per
category for RFEM 6 and RSTAB 9, so the neutral id cannot simply be used as
the object number.

This module is the boundary between the two. It walks a model in a fixed order
and asks the :class:`BackendMap` for a number per object, which allocates one
on first sight and returns the remembered one afterwards. That is what makes a
second push recognise the engineer's objects instead of replacing them.

The order matters only for how the numbers come out on a first push - readable
1..N in the order someone would expect to see them. It has no effect once a map
exists, because then every number is already decided.
"""

import os

#: Object categories, in the order a first push numbers them. RFEM keeps a
#: separate namespace per category, so each starts again at 1.
CATEGORIES = ("node", "member", "surface", "support", "line_support",
              "section", "thickness", "material", "load_case", "load")


def map_path_for(model_path, backend="rfem"):
    """Where the map for a model lives: next to it, named after the backend.

    `model.json` -> `model.rfem.json`. Findable without being told, and one
    model can be pushed to several backends without the maps colliding.
    """
    root, _ = os.path.splitext(model_path)
    return "{}.{}.json".format(root, backend)


def number_model(model, backend_map):
    """Allocate a backend number for every object in `model`.

    Idempotent: numbering the same model twice changes nothing, and numbering
    an edited model leaves the survivors' numbers alone - which is the whole
    point of the exercise.

    Parameters
    ----------
    model : :class:`StructuralModel`
    backend_map : :class:`BackendMap`
        Mutated in place, and returned for convenience.

    Returns
    -------
    :class:`BackendMap`
    """
    for node in model.nodes:
        backend_map.number_for("node", node.id)
    for member in model.members:
        backend_map.number_for("member", member.id)
    for surface in getattr(model, "surfaces", None) or []:
        backend_map.number_for("surface", surface.id)
    for support in model.supports:
        backend_map.number_for("support", support.id)
    for support in getattr(model, "line_supports", None) or []:
        backend_map.number_for("line_support", support.id)
    for section in model.sections:
        backend_map.number_for("section", section.id)
    for thickness in getattr(model, "thicknesses", None) or []:
        backend_map.number_for("thickness", thickness.id)
    for material_id in sorted(getattr(model, "materials", None) or {}):
        backend_map.number_for("material", material_id)
    for case in getattr(model, "load_cases", None) or []:
        backend_map.number_for("load_case", case.id)

    return backend_map
