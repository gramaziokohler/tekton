"""The analysis model as pictures: elements, connections, supports, loads, reactions.

Pure COMPAS - no Rhino, so it runs in pytest as well as inside Rhino. The
module decides *what* to draw and where; the Grasshopper component
(`tekton_inspect`) turns the returned specs into Rhino meshes.

A spec is a dict with a ``kind`` and whatever that kind needs, plus a
``colour`` and optionally a ``label``. Kinds:

- ``rod``       start, end, radius            - connector members
- ``sphere``    point, radius                 - hinges, shared nodes, ball supports
- ``pyramid``   apex, axis, size              - pinned support: apex at the node
- ``plate``     point, axis, size, thickness  - the plate a support sits on
- ``box``       point, axis, size             - fixed support
- ``cylinder``  point, axis, radius, length   - roller under a support plate
- ``arrow``     start, end, colour            - load or reaction, head at end
- ``arc``       point, axis, radius           - moment, drawn as a ring with a head
- ``text``      point, text                   - label
- ``slab``      points, thickness             - a surface: its mid-plane outline, extruded

Support symbols follow the engineering convention: a pinned support is a
pyramid on a plate, a roller adds cylinders under the plate along the free
direction, a ball support sits on a sphere, a fixed support is a block. The
rule is derived from the six stiffness values, not from a name, so an
authored support with an unusual combination still gets a readable symbol
and a label saying exactly what is fixed.
"""

from compas.geometry import Point
from compas.geometry import Vector
from compas.geometry import cross_vectors
from compas.geometry import normalize_vector

COLOURS = {
    "element": (214, 186, 132),
    "rigid": (50, 50, 50),
    "coupling": (190, 40, 160),
    "hinge": (15, 15, 15),      # a hinge is a black circle in every structural sketch
    "joint": (80, 80, 80),
    "support": (50, 150, 60),
    "support_free": (140, 200, 140),
    "load": (235, 120, 20),
    "moment": (200, 80, 20),
    "reaction": (40, 90, 220),
    "reaction_moment": (20, 60, 170),
}

INF = float("inf")


def is_fixed(value):
    return value == INF


def support_kind(support):
    """Classify a support by its six stiffnesses.

    Returns ``(kind, free_translations, free_rotations, springs)`` where
    kind is one of ``fixed | pinned | roller | ball | partial | free``.
    """
    trans = {axis: getattr(support, "u" + axis) for axis in "xyz"}
    rots = {axis: getattr(support, "r" + axis) for axis in "xyz"}
    springs = [k for k, v in list(("u" + a, trans[a]) for a in "xyz") + list(("r" + a, rots[a]) for a in "xyz") if v not in (0.0, INF)]
    fixed_t = [a for a in "xyz" if is_fixed(trans[a])]
    free_t = [a for a in "xyz" if not is_fixed(trans[a])]
    free_r = [a for a in "xyz" if not is_fixed(rots[a])]

    if len(fixed_t) == 3 and not free_r:
        kind = "fixed"
    elif len(fixed_t) == 3 and len(free_r) == 3:
        kind = "pinned"
    elif len(fixed_t) == 2 and len(free_r) == 3:
        kind = "roller"
    elif len(fixed_t) == 1 and len(free_r) == 3:
        kind = "ball"
    elif not fixed_t and len(free_r) == 3 and not springs:
        kind = "free"
    else:
        kind = "partial"
    return kind, free_t, free_r, springs


def support_label(support):
    kind, free_t, free_r, springs = support_kind(support)
    fixed_t = [a for a in "xyz" if a not in free_t]
    fixed_r = [a for a in "xyz" if a not in free_r]
    parts = [kind]
    if kind in ("roller", "ball"):
        parts.append("free " + "".join(free_t))
    if kind == "partial":
        parts.append("u:" + ("".join(fixed_t) or "-") + " r:" + ("".join(fixed_r) or "-"))
    if springs:
        parts.append("spring " + ",".join(springs))
    return " ".join(parts)


def _axis(name):
    return Vector(*[1.0 if a == name else 0.0 for a in "xyz"])


def support_specs(structural_model, scale=1.0, size=0.1):
    """Symbols for every supported node, in RFEM's grammar. ``size`` in model units (metres).

    - a pyramid, apex at the node, whenever some rotation is free; at its
      apex a cylinder along the one free rotation axis, or a sphere when two
      are free (three free: the bare pyramid - the classic hinge)
    - no pyramid when all rotations are fixed: the plate sits at the node
    - two rails under the symbol along a single free translation, a second
      plate below for two free translations (plate sliding on plate)
    - no translation fixed at all: no plate, a bar along every fixed
      rotation axis (a rotational clamp), nothing for a free node
    - everything fixed: a block
    """
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []
    down = Vector(0, 0, -1)
    for support in structural_model.supports:
        kind, free_t, free_r, _springs = support_kind(support)
        fixed_t = [a for a in "xyz" if a not in free_t]
        fixed_r = [a for a in "xyz" if a not in free_r]
        label = support_label(support)
        for node_id in support.nodes:
            p = points.get(node_id)
            if p is None:
                continue
            node = _scaled(p, scale)
            s = size * scale
            colour = COLOURS["support"] if kind != "free" else COLOURS["support_free"]

            if not fixed_t:
                # Rotational clamp only: a bar along each fixed rotation axis.
                for a in fixed_r:
                    axis = _axis(a)
                    specs.append({"kind": "rod", "start": _offset(node, axis, -s), "end": _offset(node, axis, s), "radius": s * 0.08, "colour": colour})
                if fixed_r:
                    specs.append({"kind": "text", "point": _offset(node, down, s * 1.4), "text": label, "colour": colour})
                continue

            if kind == "fixed":
                specs.append({"kind": "box", "point": _offset(node, down, s * 0.5), "axis": down, "size": s, "colour": colour})
                specs.append({"kind": "text", "point": _offset(node, down, s * 1.4), "text": label, "colour": colour})
                continue

            depth = 0.0  # how far below the node the symbol has grown so far
            if free_r:
                specs.append({"kind": "pyramid", "apex": node, "axis": down, "size": s, "colour": colour})
                depth = s
                if len(free_r) == 1:
                    specs.append({"kind": "cylinder", "point": node, "axis": _axis(free_r[0]), "radius": s * 0.22, "length": s * 0.9, "colour": colour})
                elif len(free_r) == 2:
                    specs.append({"kind": "sphere", "point": node, "radius": s * 0.25, "colour": colour})
            specs.append({"kind": "plate", "point": _offset(node, down, depth), "axis": down, "size": s * 1.3, "thickness": s * 0.08, "colour": colour})
            depth += s * 0.08

            if len(free_t) == 1:
                free = _axis(free_t[0])
                across = Vector(*cross_vectors(free, down)) if free_t[0] != "z" else Vector(1, 0, 0)
                for side in (-0.4, 0.4):
                    centre = _offset(_offset(node, down, depth + s * 0.1), across, s * side)
                    specs.append({"kind": "rod", "start": _offset(centre, free, -s * 0.7), "end": _offset(centre, free, s * 0.7), "radius": s * 0.07, "colour": colour})
                depth += s * 0.2
            elif len(free_t) == 2:
                depth += s * 0.15
                specs.append({"kind": "plate", "point": _offset(node, down, depth), "axis": down, "size": s * 1.3, "thickness": s * 0.08, "colour": colour})
                depth += s * 0.08

            specs.append({"kind": "text", "point": _offset(node, down, depth + s * 0.4), "text": label, "colour": colour})
    return specs


def connection_specs(structural_model, scale=1.0, size=0.1):
    """Connector members as rods, hinged ends as spheres, shared beam nodes as small spheres."""
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []
    s = size * scale
    beams_at_node = {}
    for member in structural_model.members:
        if member.member_type == "BEAM":
            for node_id in (member.node_start, member.node_end):
                beams_at_node.setdefault(node_id, set()).add(member.source_element_id)
            continue
        a, b = points.get(member.node_start), points.get(member.node_end)
        if a is None or b is None:
            continue
        rigid = member.member_type == "RIGID" or (member.release_start is None and member.release_end is None)
        colour = COLOURS["rigid"] if rigid else COLOURS["coupling"]
        # A connector is short (the offset between two system lines, a few
        # centimetres). A rod thicker than it is long reads as a blob, so the
        # diameter is capped at a third of the length, the hinge marker at
        # two thirds; the symbol size only sets the upper bound.
        length = a.distance_to_point(b) * scale
        rod_radius = min(s * 0.18, length / 6.0)
        hinge_radius = min(s * 0.16, length / 3.0)
        specs.append({"kind": "rod", "start": _scaled(a, scale), "end": _scaled(b, scale), "radius": rod_radius, "colour": colour,
                      "label": "rigid" if rigid else "coupling"})
        for release, p in ((member.release_start, a), (member.release_end, b)):
            if release is not None and not release.is_rigid():
                specs.append({"kind": "sphere", "point": _scaled(p, scale), "radius": hinge_radius, "colour": COLOURS["hinge"],
                              "label": "hinge " + "/".join(release.released_dofs())})
    # Nodes where two different beams meet on the axis: a continuous joint.
    for node_id, beams in beams_at_node.items():
        if len(beams) > 1 and node_id in points:
            specs.append({"kind": "sphere", "point": _scaled(points[node_id], scale), "radius": s * 0.08, "colour": COLOURS["joint"], "label": "shared node"})
    return specs


def load_specs(structural_model, load_case_id=None, scale=1.0, size=0.1, per_kn=0.5, per_knm=0.3):
    """Arrows for point loads, arrow rows for member loads, rings for moments.

    ``per_kn`` is arrow length per kN (model units), ``per_knm`` ring radius
    per kNm. Loads of other load cases are skipped when ``load_case_id`` is
    given.
    """
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []
    s = size * scale

    for load in structural_model.point_loads:
        if load_case_id is not None and load.load_case_id != load_case_id:
            continue
        p = points.get(load.node_id)
        if p is None:
            continue
        tip = _scaled(p, scale)
        f = Vector(*load.force)
        if f.length > 1e-9:
            start = _offset(tip, f.unitized(), -f.length * per_kn * scale)
            specs.append({"kind": "arrow", "start": start, "end": tip, "colour": COLOURS["load"], "label": "{:.3g} kN".format(f.length)})
        m = Vector(*load.moment) if load.moment is not None else Vector(0, 0, 0)
        if m.length > 1e-9:
            specs.append({"kind": "arc", "point": tip, "axis": m.unitized(), "radius": max(m.length * per_knm, s * 0.5) * scale,
                          "colour": COLOURS["moment"], "label": "{:.3g} kNm".format(m.length)})

    for load in structural_model.member_loads:
        if load_case_id is not None and load.load_case_id != load_case_id:
            continue
        member = next((m for m in structural_model.members if m.id == load.member_id), None)
        if member is None:
            continue
        a, b = points.get(member.node_start), points.get(member.node_end)
        if a is None or b is None:
            continue
        f = Vector(*load.force)
        if f.length < 1e-9:
            continue
        length = f.length * per_kn * scale
        direction = f.unitized()
        t0, t1 = float(load.dist_start), float(load.dist_end)
        n = max(2, int(round(3 + 6 * (t1 - t0))))
        tips = []
        for i in range(n):
            t = t0 + (t1 - t0) * i / (n - 1)
            tip = _scaled(Point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t), scale)
            tips.append(tip)
            specs.append({"kind": "arrow", "start": _offset(tip, direction, -length), "end": tip, "colour": COLOURS["load"]})
        # The bar joining the arrow tails: the load block.
        specs.append({"kind": "rod", "start": _offset(tips[0], direction, -length), "end": _offset(tips[-1], direction, -length),
                      "radius": s * 0.03, "colour": COLOURS["load"], "label": "{:.3g} kN/m".format(f.length)})
        mid = tips[len(tips) // 2]
        specs.append({"kind": "text", "point": _offset(mid, direction, -length - s * 0.3), "text": "{:.3g} kN/m".format(f.length), "colour": COLOURS["load"]})

    specs.extend(_surface_load_specs(structural_model, load_case_id, scale, s, per_kn))

    return specs


def _surface_load_specs(structural_model, load_case_id, scale, s, per_kn):
    """A grid of arrows over a loaded plate.

    Drawn from the plate's outline, not from its mesh: the mesh belongs to
    whichever backend is running and may not exist at all when this is
    called. A fixed handful of arrows says "this plate carries a pressure"
    without pretending to show a distribution.
    """
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []

    for load in getattr(structural_model, "surface_loads", None) or []:
        if load_case_id is not None and load.load_case_id != load_case_id:
            continue
        surface = next((s_ for s_ in structural_model.surfaces if s_.id == load.surface_id), None)
        if surface is None:
            continue
        corners = [points[i] for i in surface.nodes if i in points]
        if len(corners) < 3:
            continue
        pressure = Vector(*load.pressure)
        if pressure.length < 1e-9:
            continue

        direction = pressure.unitized()
        length = pressure.length * per_kn * scale
        for anchor in _grid_over(corners):
            tip = _scaled(anchor, scale)
            specs.append({"kind": "arrow", "start": _offset(tip, direction, -length), "end": tip,
                          "colour": COLOURS["load"]})

        centre = Point(
            sum(c.x for c in corners) / len(corners),
            sum(c.y for c in corners) / len(corners),
            sum(c.z for c in corners) / len(corners),
        )
        label = "{:.3g} kN/m2".format(pressure.length)
        if getattr(load, "projected", False):
            label += " (projected)"
        specs.append({"kind": "text",
                      "point": _offset(_scaled(centre, scale), direction, -length - s * 0.3),
                      "text": label, "colour": COLOURS["load"]})
    return specs


def _grid_over(corners, divisions=3):
    """A few points spread inside a polygon, for hanging arrows on.

    Bilinear over the outline's bounding corners and filtered to what is
    inside - good enough for a symbol, and it costs nothing on a plate with
    a hundred outline vertices.
    """
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    out = []
    for i in range(1, divisions + 1):
        for j in range(1, divisions + 1):
            u = i / (divisions + 1.0)
            v = j / (divisions + 1.0)
            x = min(xs) + (max(xs) - min(xs)) * u
            y = min(ys) + (max(ys) - min(ys)) * v
            # A plate is planar, so z follows from the other two on a tilted
            # one; for a flat plate every z is the same anyway.
            z = min(zs) + (max(zs) - min(zs)) * v
            if _inside(corners, x, y):
                out.append(Point(x, y, z))
    return out or [Point(sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))]


def _inside(corners, x, y):
    """Point in polygon, in plan. Ray casting."""
    inside = False
    count = len(corners)
    for index in range(count):
        a = corners[index]
        b = corners[(index + 1) % count]
        if (a.y > y) != (b.y > y):
            if abs(b.y - a.y) > 1e-12:
                crossing = a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y)
                if x < crossing:
                    inside = not inside
    return inside


def reaction_specs(structural_model, load_case_id=None, scale=1.0, size=0.1, per_kn=0.5, per_knm=0.3):
    """Support reactions as arrows pointing *into* the node (the support pushes back)."""
    results = structural_model.results or {}
    if not results:
        return []
    case_id = load_case_id if load_case_id is not None else sorted(results)[0]
    result_set = results.get(case_id)
    if result_set is None:
        return []
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []
    s = size * scale
    for node_id, result in (result_set.node_results or {}).items():
        force = result.reaction_force
        if force is None:
            continue
        p = points.get(node_id)
        if p is None:
            continue
        tip = _scaled(p, scale)
        f = Vector(*force)
        if f.length > 1e-6:
            specs.append({"kind": "arrow", "start": _offset(tip, f.unitized(), -f.length * per_kn * scale), "end": tip,
                          "colour": COLOURS["reaction"],
                          "label": "R = {:.3g} kN ({:+.2g}, {:+.2g}, {:+.2g})".format(f.length, f.x, f.y, f.z)})
        m = Vector(*result.reaction_moment) if result.reaction_moment is not None else Vector(0, 0, 0)
        if m.length > 1e-6:
            specs.append({"kind": "arc", "point": tip, "axis": m.unitized(), "radius": max(m.length * per_knm, s * 0.5) * scale,
                          "colour": COLOURS["reaction_moment"], "label": "M = {:.3g} kNm".format(m.length)})
    return specs


def surface_specs(structural_model, scale=1.0):
    """Surfaces as their mid-plane outline with the thickness, one spec each."""
    points = {n.id: n.point for n in structural_model.nodes}
    thicknesses = {t.id: t.thickness for t in structural_model.thicknesses}
    specs = []
    for surface in structural_model.surfaces:
        outline = [points.get(n) for n in surface.nodes]
        if any(p is None for p in outline) or len(outline) < 3:
            continue
        specs.append({"kind": "slab", "points": [_scaled(p, scale) for p in outline],
                      "thickness": thicknesses.get(surface.thickness_id, 0.0) * scale, "colour": COLOURS["element"]})
    return specs


def surface_connection_specs(structural_model, scale=1.0, size=0.1):
    """Surface-to-surface connections as rods along the shared edge; hinged edges in the coupling colour."""
    points = {n.id: n.point for n in structural_model.nodes}
    specs = []
    s = size * scale
    for connection in structural_model.surface_connections:
        nodes = [points.get(n) for n in connection.nodes]
        if any(p is None for p in nodes) or len(nodes) < 2:
            continue
        release = connection.release
        rigid = release is None or release.is_rigid()
        colour = COLOURS["rigid"] if rigid else COLOURS["coupling"]
        label = "rigid edge" if rigid else "edge hinge " + "/".join(release.released_dofs())
        for a, b in zip(nodes, nodes[1:]):
            specs.append({"kind": "rod", "start": _scaled(a, scale), "end": _scaled(b, scale), "radius": s * 0.12, "colour": colour, "label": label})
    return specs


def element_specs(structural_model, scale=1.0):
    """Beam members as section sweeps (straight), one spec per member."""
    points = {n.id: n.point for n in structural_model.nodes}
    sections = {sec.id: sec for sec in structural_model.sections}
    specs = []
    for member in structural_model.members:
        if member.member_type != "BEAM":
            continue
        section = sections.get(member.section_id)
        a, b = points.get(member.node_start), points.get(member.node_end)
        if section is None or a is None or b is None or section.width <= 0:
            continue
        specs.append({"kind": "beam", "start": _scaled(a, scale), "end": _scaled(b, scale),
                      "width": section.width * scale, "height": section.height * scale,
                      "orientation": Vector(*member.orientation_vector), "colour": COLOURS["element"]})
    return specs


def legend(structural_model, load_case_id=None):
    supports = {}
    for support in structural_model.supports:
        supports[support_label(support)] = supports.get(support_label(support), 0) + len(support.nodes)
    kinds = {}
    for member in structural_model.members:
        kinds[member.member_type] = kinds.get(member.member_type, 0) + 1
    lines = ["Members: " + (", ".join("{} {}".format(v, k.lower()) for k, v in sorted(kinds.items())) or "none")]
    if structural_model.surfaces:
        lines.append("Surfaces: {} ({} edge connections)".format(len(structural_model.surfaces), len(structural_model.surface_connections)))
    lines.append("Supports: " + (", ".join("{}x {}".format(v, k) for k, v in sorted(supports.items())) or "none"))
    n_point = sum(1 for l in structural_model.point_loads if load_case_id is None or l.load_case_id == load_case_id)
    n_member = sum(1 for l in structural_model.member_loads if load_case_id is None or l.load_case_id == load_case_id)
    lines.append("Loads{}: {} point, {} member".format("" if load_case_id is None else " LC{}".format(load_case_id), n_point, n_member))
    self_weight = [lc.name for lc in structural_model.load_cases if getattr(lc, "self_weight", False)]
    if self_weight:
        lines.append("Self-weight: " + ", ".join(self_weight))
    return lines


def _scaled(p, scale):
    return Point(p[0] * scale, p[1] * scale, p[2] * scale)


def _offset(p, direction, distance):
    d = normalize_vector(list(direction)) if _length(direction) > 1e-12 else [0, 0, 0]
    return Point(p[0] + d[0] * distance, p[1] + d[1] * distance, p[2] + d[2] * distance)


def _length(v):
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


__all__ = [
    "COLOURS",
    "support_kind",
    "support_label",
    "support_specs",
    "connection_specs",
    "load_specs",
    "reaction_specs",
    "element_specs",
    "surface_specs",
    "surface_connection_specs",
    "legend",
]
