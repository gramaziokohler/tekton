"""A short hash over everything that changes the answer.

What for: results outlive the model they were computed from. Grasshopper holds
on to old outputs, a JSON on disk says nothing about when it was written, and a
number that looks current while describing a model that no longer exists is the
worst failure mode in this workflow. Every calculation is stamped with the
fingerprint of the model it was given; the result components compare that stamp
against the model on the canvas and warn 'stale' when it differs.

The rule that decides what goes in: **would an engineer expect a different
answer?** If yes it belongs in the hash, and leaving it out produces a *false
fresh* - stale numbers keeping their authority. If no it must stay out, because
a *false stale* trains people to ignore the warning.

By that rule the hash covers geometry, topology, sections, thicknesses,
materials with their properties, releases, eccentricities, supports, load cases,
every kind of load, combination factors, span directions, openings and the
source unit. It deliberately excludes:

* **ids** - they derive from graph order today (WP6), so an unrelated edit
  renumbers a structure that has not moved. Topology enters as *positions*
  instead: a member is the pair of points it connects.
* **provenance** - source GUIDs record where an object came from, not what it
  does mechanically.
* **results** - a model with its results in it is the same model; hashing them
  would mean a stamp could never match the model it came from.

Coordinates are rounded before hashing. Unrounded floats made the last bit of a
unit conversion flip the hash, so a re-translated model looked edited. The
tolerance is coarse enough to swallow that noise and fine enough to keep a
millimetre - which is a real edit in timber.
"""

import hashlib
import json
import math

#: Coordinates are rounded to this many decimals (metres) before hashing, so
#: float noise from unit conversion does not read as a design change. Six
#: decimals is a thousandth of a millimetre: below anything a timber model
#: means, above anything a conversion introduces.
COORDINATE_DECIMALS = 6

#: Stiffnesses and load magnitudes are rounded the same way. They are kN, kNm
#: and kN/m, so this is far below any meaningful load step.
VALUE_DECIMALS = 6

#: Length of the returned digest. Short enough to print on a component message,
#: long enough that a collision is not a practical concern for one session's
#: worth of models.
DIGEST_LENGTH = 12


def model_fingerprint(structural_model):
    """Short hash over everything in the model that changes the answer.

    Parameters
    ----------
    structural_model : :class:`StructuralModel`
        The model as it was handed to a backend.

    Returns
    -------
    str
        A 12-character hex digest. Equal digests mean the two models produce
        the same analysis; different digests mean something mechanically
        relevant differs.
    """
    payload = fingerprint_payload(structural_model)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:DIGEST_LENGTH]


def fingerprint_payload(model):
    """The structure that gets hashed, as plain JSON-safe data.

    Separate from :func:`model_fingerprint` so a difference can be *inspected*:
    when two models disagree, diffing their payloads says which part changed.
    """
    nodes = {node.id: _point(node.point) for node in getattr(model, "nodes", None) or []}

    return {
        # Node positions only - the id is the lookup key here, not content.
        "nodes": _ordered(nodes.values()),
        "members": _ordered(_member(member, nodes) for member in getattr(model, "members", None) or []),
        "surfaces": _ordered(_surface(surface, nodes) for surface in getattr(model, "surfaces", None) or []),
        "surface_connections": _ordered(
            _connection(connection, nodes) for connection in getattr(model, "surface_connections", None) or []
        ),
        "sections": _ordered(_section(section) for section in getattr(model, "sections", None) or []),
        "thicknesses": _ordered(_thickness(thickness) for thickness in getattr(model, "thicknesses", None) or []),
        "materials": _ordered(_material(material) for material in (getattr(model, "materials", None) or {}).values()),
        "supports": _ordered(_support(support, nodes) for support in getattr(model, "supports", None) or []),
        "load_cases": _ordered(_load_case(case) for case in getattr(model, "load_cases", None) or []),
        "load_combinations": _ordered(
            _combination(combination) for combination in getattr(model, "load_combinations", None) or []
        ),
        "point_loads": _ordered(_point_load(load, nodes) for load in getattr(model, "point_loads", None) or []),
        "member_loads": _ordered(_member_load(load, model, nodes) for load in getattr(model, "member_loads", None) or []),
        "surface_loads": _ordered(
            _surface_load(load, model, nodes) for load in getattr(model, "surface_loads", None) or []
        ),
        "source_units": getattr(model, "source_units", "m"),
    }


# --- the pieces -----------------------------------------------------------
#
# Every helper returns a JSON-safe structure. Ordering them is what makes the
# hash independent of list order: the iteration order of the structural graph
# is an accident of how it was built, not a property of the structure.


def _key(item):
    """A total order over any JSON-safe structure.

    Sorting the structures directly breaks as soon as two entries differ in
    shape - a support pointing at a missing node yields ``None`` next to a
    coordinate list, and ``None < list`` raises. That happens in models that
    are malformed, which are exactly the models someone is debugging, so the
    fingerprint has to survive them rather than raise.
    """
    return json.dumps(item, sort_keys=True, separators=(",", ":"))


def _ordered(items):
    """Order-independent list of JSON-safe entries."""
    return sorted(items, key=_key)


def _num(value):
    """Round a scalar, and keep infinity JSON-safe.

    ``inf`` means rigid throughout the neutral model, so it has to survive as
    a distinguishable value rather than as ``Infinity``, which is not valid
    JSON in strict mode.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    if math.isnan(number):
        return "nan"
    return round(number, VALUE_DECIMALS)


def _point(point):
    if point is None:
        return None
    return [round(float(coordinate), COORDINATE_DECIMALS) for coordinate in list(point)[:3]]


def _vector(vector):
    return _point(vector)


def _at(node_id, nodes):
    """A node id resolved to its position - the id itself is not content."""
    return nodes.get(node_id)


def _ring(node_ids, nodes):
    """A closed ring of nodes, rotation-independent.

    The same ring can start at any of its vertices depending on how it was
    built, so it is normalised to its smallest rotation. Direction is kept:
    a reversed ring flips a surface normal, which is mechanically real.
    """
    points = [_at(node_id, nodes) for node_id in node_ids or []]
    if not points:
        return []
    keys = [_key(point) for point in points]
    best = min(range(len(keys)), key=lambda i: keys[i:] + keys[:i])
    return points[best:] + points[:best]


def _release(release):
    if release is None:
        return None
    return [_num(getattr(release, dof, None)) for dof in ("ux", "uy", "uz", "rx", "ry", "rz")]


def _eccentricity(eccentricity):
    if eccentricity is None:
        return None
    return [_vector(getattr(eccentricity, "start", None)), _vector(getattr(eccentricity, "end", None))]


def _member(member, nodes):
    return [
        _at(member.node_start, nodes),
        _at(member.node_end, nodes),
        member.section_id,
        _vector(getattr(member, "orientation_vector", None)),
        bool(getattr(member, "is_rigid", False)),
        getattr(member, "member_type", "BEAM"),
        _release(getattr(member, "release_start", None)),
        _release(getattr(member, "release_end", None)),
        _eccentricity(getattr(member, "eccentricity", None)),
    ]


def _surface(surface, nodes):
    return [
        _ring(surface.nodes, nodes),
        surface.thickness_id,
        _ordered(_ring(opening, nodes) for opening in getattr(surface, "openings", None) or []),
        _vector(getattr(surface, "span_direction", None)),
    ]


def _connection(connection, nodes):
    return [
        [_at(node_id, nodes) for node_id in connection.nodes or []],
        _release(getattr(connection, "release", None)),
    ]


def _section(section):
    return [
        section.material_id,
        _num(getattr(section, "width", 0.0)),
        _num(getattr(section, "height", 0.0)),
        getattr(section, "shape_type", "rectangular"),
    ]


def _thickness(thickness):
    return [thickness.material_id, _num(getattr(thickness, "thickness", 0.0))]


def _material(material):
    """Grade name plus the properties that reach a solver.

    The name alone is not enough: an edited strength at an unchanged grade name
    is exactly the silent change this hash exists to catch. Older serialised
    models carry a bare string instead of a Material object.
    """
    if isinstance(material, str):
        return [material]
    properties = [
        "standard",
        "density_mean",
        "density_k",
        "f_mk",
        "f_vk",
        "poisson",
    ]
    out = [str(getattr(material, "name", material))]
    for name in properties:
        value = getattr(material, name, None)
        out.append(value if isinstance(value, str) else _num(value))
    # Anything else the Material carries - E and G moduli differ by class and
    # are not worth enumerating by hand, but they do change the answer.
    extra = []
    for key, value in sorted(vars(material).items()) if hasattr(material, "__dict__") else []:
        if key in properties or key == "name":
            continue
        extra.append([key, value if isinstance(value, str) else _num(value)])
    out.append(extra)
    return out


def _support(support, nodes):
    return [
        _ordered(_at(node_id, nodes) for node_id in support.nodes or []),
        _num(support.ux),
        _num(support.uy),
        _num(support.uz),
        _num(support.rx),
        _num(support.ry),
        _num(support.rz),
    ]


def _load_case(case):
    # The id is content here: loads reference their case by it, and the
    # combination factors are keyed by it.
    return [case.id, case.name, getattr(case, "action_category", "PERMANENT"), bool(getattr(case, "self_weight", False))]


def _combination(combination):
    factors = getattr(combination, "factors", None) or {}
    return [
        combination.id,
        combination.name,
        getattr(combination, "combination_type", "ULS"),
        _ordered([str(case_id), _num(factor)] for case_id, factor in factors.items()),
    ]


def _point_load(load, nodes):
    return [
        _at(load.node_id, nodes),
        load.load_case_id,
        _vector(getattr(load, "force", None)),
        _vector(getattr(load, "moment", None)),
    ]


def _member_load(load, model, nodes):
    """A member load, addressed by the member's geometry rather than its id."""
    member = _find(getattr(model, "members", None), load.member_id)
    where = _member(member, nodes)[:2] if member else load.member_id
    return [
        where,
        load.load_case_id,
        _vector(getattr(load, "force", None)),
        _num(getattr(load, "dist_start", 0.0)),
        _num(getattr(load, "dist_end", 1.0)),
    ]


def _surface_load(load, model, nodes):
    surface = _find(getattr(model, "surfaces", None), load.surface_id)
    where = _ring(surface.nodes, nodes) if surface else load.surface_id
    return [
        where,
        load.load_case_id,
        _vector(getattr(load, "pressure", None)),
        bool(getattr(load, "projected", False)),
    ]


def _find(items, item_id):
    for item in items or []:
        if item.id == item_id:
            return item
    return None
