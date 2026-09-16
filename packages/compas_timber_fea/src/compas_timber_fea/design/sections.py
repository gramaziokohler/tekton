"""Cross-section properties and member length.

Pure geometry, no engineering assumption - but missing from the neutral
model until now, which is why the checks could not be written. Everything is
SI, consistent with ``core/units.py``: lengths in metres, so areas are m2,
second moments m4 and section moduli m3.
"""

import math

#: Shear stress distribution factor: tau_max / tau_mean.
#: 1.5 for a rectangle, 4/3 for a solid circle (6.1.7).
_SHEAR_FACTOR_RECTANGULAR = 1.5
_SHEAR_FACTOR_CIRCULAR = 4.0 / 3.0


def section_properties(section):
    """Geometric properties of a :class:`StructuralSection`.

    Supports the shapes the translator produces: rectangular (the timber
    default) and circular. Anything else falls back to the rectangular
    formulas using width and height as a bounding box, and says so through
    ``is_approximated`` - a wrong-but-labelled property beats a crash in a
    report that is meant to be read.

    Returns
    -------
    dict
        ``area`` (m2), ``I_y``/``I_z`` (m4), ``W_y``/``W_z`` (m3),
        ``shear_factor``, ``shape``, ``is_approximated``.

    Notes
    -----
    The y axis is the strong axis: bending about y uses the section modulus
    formed with the height, matching ``moment_y`` in the result model.
    """
    width = float(getattr(section, "width", 0.0) or 0.0)
    height = float(getattr(section, "height", 0.0) or 0.0)
    shape = (getattr(section, "shape_type", "") or "rectangular").lower()

    if width <= 0 or height <= 0:
        raise ValueError(
            "Section {!r} has no usable dimensions (width={}, height={}).".format(
                getattr(section, "name", getattr(section, "id", "?")), width, height
            )
        )

    if shape.startswith("circ") or shape.startswith("round"):
        diameter = min(width, height)
        radius = diameter / 2.0
        area = math.pi * radius ** 2
        second_moment = math.pi * diameter ** 4 / 64.0
        modulus = math.pi * diameter ** 3 / 32.0
        return {
            "area": area,
            "I_y": second_moment,
            "I_z": second_moment,
            "W_y": modulus,
            "W_z": modulus,
            "shear_factor": _SHEAR_FACTOR_CIRCULAR,
            "shape": "circular",
            "is_approximated": False,
        }

    area = width * height
    return {
        "area": area,
        "I_y": width * height ** 3 / 12.0,
        "I_z": height * width ** 3 / 12.0,
        "W_y": width * height ** 2 / 6.0,
        "W_z": height * width ** 2 / 6.0,
        "shear_factor": _SHEAR_FACTOR_RECTANGULAR,
        "shape": "rectangular",
        "is_approximated": not (shape.startswith("rect") or shape == ""),
    }


def member_length(model, member):
    """Distance between a member's end nodes, in metres.

    Returns 0.0 when a node is missing rather than raising: a length is used
    for slenderness and for span/deflection ratios, both of which are
    reported as "unknown" rather than aborting a whole report.
    """
    nodes = {node.id: node for node in getattr(model, "nodes", [])}
    start = nodes.get(getattr(member, "node_start", None))
    end = nodes.get(getattr(member, "node_end", None))
    if start is None or end is None:
        return 0.0
    try:
        return math.sqrt(
            (end.point[0] - start.point[0]) ** 2
            + (end.point[1] - start.point[1]) ** 2
            + (end.point[2] - start.point[2]) ** 2
        )
    except (TypeError, IndexError, AttributeError):
        return 0.0
