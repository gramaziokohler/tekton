"""Area loads on beam grids, and beam-relative ranges of line loads.

A roof or floor framed as a beam grid has no plates, so a pressure in kN/m2
cannot go onto a surface - it has to become line loads on the members that
frame each field. This module does that on the translated model, because only
there do the members exist that a beam was split into (one per field edge).

The panels are the faces of the planar graph that the horizontal members of
one level form. Each panel hands its load to its edges:

- a rectangle by the 45-degree rule, as the uniform load of equal total
  (square of side l: q*l/4 on each edge),
- any other shape by the centroid rule: each edge carries the triangle
  between it and the centroid (for a square this is the same q*l/4).

The total is conserved either way - the loads on the edges add up to pressure
times panel area - which is what makes the result checkable at a glance.

Which panels are loaded is decided in plan: a panel is in when its centroid
lies inside the regions by the even-odd rule, so an outline plus an inner
curve is the ring between them (a canopy around a supported field).

Pure Python, no Rhino and no Python 3.10 syntax: it runs inside Rhino too.
"""

import math


def _signed_area(points):
    area = 0.0
    for i in range(len(points)):
        x0, y0 = points[i][0], points[i][1]
        x1, y1 = points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1]
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def _centroid(points):
    a = _signed_area(points)
    if abs(a) < 1e-12:
        n = float(len(points))
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
    cx = cy = 0.0
    for i in range(len(points)):
        x0, y0 = points[i][0], points[i][1]
        x1, y1 = points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return (cx / (6.0 * a), cy / (6.0 * a))


def point_in_regions(point, regions):
    """Even-odd test in plan: inside an odd number of the closed polygons."""
    x, y = point[0], point[1]
    inside = False
    for polygon in regions:
        n = len(polygon)
        for i in range(n):
            x0, y0 = polygon[i][0], polygon[i][1]
            x1, y1 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
            if (y0 > y) != (y1 > y):
                if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                    inside = not inside
    return inside


# --- the level ----------------------------------------------------------------

def level_members(model, level=None, tol=1e-3):
    """Horizontal beam members of one level: (z, [(member, start, end), ...]).

    Without `level` the highest level that carries horizontal members is
    taken - the roof. Rigid links and couplings are left out: they frame no
    field.
    """
    nodes = {node.id: node.point for node in model.nodes}
    horizontal = []
    for member in model.members:
        if getattr(member, "member_type", "BEAM") != "BEAM":
            continue
        a, b = nodes.get(member.node_start), nodes.get(member.node_end)
        if a is None or b is None:
            continue
        if abs(a[2] - b[2]) > tol:
            continue
        if math.hypot(b[0] - a[0], b[1] - a[1]) < tol:
            continue
        horizontal.append((member, a, b))
    if not horizontal:
        return None, []
    if level is None:
        level = max(0.5 * (a[2] + b[2]) for _, a, b in horizontal)
    return level, [(m, a, b) for m, a, b in horizontal if abs(0.5 * (a[2] + b[2]) - level) <= tol]


# --- the panels -----------------------------------------------------------------

def find_panels(edges, tol=1e-3):
    """The bounded faces of a planar graph.

    `edges` is a list of (member_id, start, end) with 3D points; ends closer
    than `tol` are one node. Returns (panels, pruned): each panel a dict with
    the counter-clockwise `points` and the `edges` [(member_id, a, b), ...]
    along them; `pruned` counts the dangling edges removed first (a member
    with a free end frames no field).
    """
    keys = {}
    positions = []

    def key_of(p):
        k = (int(round(p[0] / tol)), int(round(p[1] / tol)))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                hit = keys.get((k[0] + dx, k[1] + dy))
                if hit is not None:
                    return hit
        keys[k] = len(positions)
        positions.append((p[0], p[1]))
        return keys[k]

    adjacency = {}
    for member_id, a, b in edges:
        u, v = key_of(a), key_of(b)
        if u == v:
            continue
        adjacency.setdefault(u, {})[v] = member_id
        adjacency.setdefault(v, {})[u] = member_id

    # Dangling edges first: a tree branch would show up as a spike in a face.
    pruned = 0
    changed = True
    while changed:
        changed = False
        for u in list(adjacency):
            if len(adjacency[u]) == 1:
                (v,) = adjacency[u].keys()
                del adjacency[v][u]
                del adjacency[u]
                pruned += 1
                changed = True
            elif not adjacency[u]:
                del adjacency[u]

    def angle(u, v):
        return math.atan2(positions[v][1] - positions[u][1], positions[v][0] - positions[u][0])

    ordered = {u: sorted(nbrs, key=lambda v, u=u: angle(u, v)) for u, nbrs in adjacency.items()}

    visited = set()
    panels = []
    for u in ordered:
        for v in ordered[u]:
            if (u, v) in visited:
                continue
            loop = []
            a, b = u, v
            while (a, b) not in visited:
                visited.add((a, b))
                loop.append((a, b))
                around = ordered[b]
                i = around.index(a)
                # The neighbour just before `a` in counter-clockwise order:
                # the face on the left of a->b, closed counter-clockwise.
                a, b = b, around[i - 1]
            points = [positions[s] for s, _ in loop]
            if _signed_area(points) <= 1e-9:
                continue  # the outer face, or a degenerate one
            panels.append({
                "points": points,
                "edges": [(adjacency[s][t], positions[s], positions[t]) for s, t in loop],
            })
    return panels, pruned


def _sides(points, tol=1e-6):
    """Corner indices of a polygon, collinear vertices dropped."""
    n = len(points)
    corners = []
    for i in range(n):
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
        scale = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if scale and abs(cross) / scale > tol:
            corners.append(i)
    return corners


def edge_widths(panel):
    """Tributary width per panel edge: line load = pressure * width.

    Returns (widths parallel to panel['edges'], rule) with rule '45deg' for a
    rectangle and 'centroid' otherwise.
    """
    points = panel["points"]
    corners = _sides(points)
    if len(corners) == 4:
        c = [points[i] for i in corners]
        sides = [(c[k], c[(k + 1) % 4]) for k in range(4)]
        lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in sides]
        right = True
        for k in range(4):
            a, b = sides[k]
            _, d = sides[(k + 1) % 4]
            dot = (b[0] - a[0]) * (d[0] - b[0]) + (b[1] - a[1]) * (d[1] - b[1])
            if abs(dot) > 1e-6 * lengths[k] * lengths[(k + 1) % 4]:
                right = False
        if right:
            s = min(lengths)
            ab = lengths[0] * lengths[1]
            t_short = s * s / 4.0
            t_long = (ab - 2.0 * t_short) / 2.0
            # Which side each edge lies on: walk the corners in order.
            widths = []
            side = -1
            corner_set = set(corners)
            first = corners[0]
            for k in range(len(points)):
                index = (first + k) % len(points)
                if index in corner_set:
                    side += 1
                length = lengths[side]
                total = t_short if abs(length - s) < 1e-9 * max(1.0, s) else t_long
                widths.append((index, total / length))
            by_index = dict(widths)
            return [by_index[i] for i in range(len(points))], "45deg"

    centroid = _centroid(points)
    widths = []
    for (_, a, b) in panel["edges"]:
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        # Height of the triangle (a, b, centroid) over the edge.
        cross = (b[0] - a[0]) * (centroid[1] - a[1]) - (b[1] - a[1]) * (centroid[0] - a[0])
        widths.append(abs(cross) / length / 2.0 if length else 0.0)
    return widths, "centroid"


def distribute_area_load(model, pressure, regions=None, level=None, tol=1e-3):
    """Line loads on the members framing the loaded panels.

    Parameters
    ----------
    model : StructuralModel
    pressure : sequence of 3 floats
        kN/m2 as a vector; (0, 0, -3) is 3 kN/m2 downward.
    regions : list of polygons, optional
        Plan polygons [(x, y[, z]), ...] in metres. Even-odd; none = every
        panel of the level.
    level : float, optional
        z of the beam grid in metres. None = the highest one.

    Returns
    -------
    (loads, info)
        loads: {member_id: (fx, fy, fz)} in kN/m, summed over the panels.
        info: what was found and how much went where.
    """
    z, members = level_members(model, level=level, tol=tol)
    info = {"level": z, "panels": 0, "panels_loaded": 0, "area": 0.0, "total": 0.0,
            "members": 0, "pruned": 0, "rules": {}}
    if not members:
        return {}, info
    edges = [(m.id, a, b) for m, a, b in members]
    panels, pruned = find_panels(edges, tol=tol)
    info["panels"] = len(panels)
    info["pruned"] = pruned

    px, py, pz = float(pressure[0]), float(pressure[1]), float(pressure[2])
    magnitude = math.sqrt(px * px + py * py + pz * pz)
    loads = {}
    for panel in panels:
        if regions and not point_in_regions(_centroid(panel["points"]), regions):
            continue
        widths, rule = edge_widths(panel)
        info["rules"][rule] = info["rules"].get(rule, 0) + 1
        info["panels_loaded"] += 1
        area = _signed_area(panel["points"])
        info["area"] += area
        for (member_id, a, b), width in zip(panel["edges"], widths):
            f = loads.get(member_id, (0.0, 0.0, 0.0))
            loads[member_id] = (f[0] + px * width, f[1] + py * width, f[2] + pz * width)
    info["total"] = magnitude * info["area"]
    info["members"] = len(loads)
    return loads, info


# --- beam-relative ranges -----------------------------------------------------------

def element_ranges(model, member_ids):
    """Where each member lies along the element it came from: {id: (t0, t1, flipped)}.

    Relative 0..1 over the element's extent, measured along the first
    member's direction. A beam split at its joints becomes a chain of
    members; a line load given as 0.2..0.4 of the beam has to land on the
    pieces that cover that stretch, not on 0.2..0.4 of every piece.
    """
    nodes = {node.id: node.point for node in model.nodes}
    by_id = {member.id: member for member in model.members}
    chain = [by_id[i] for i in member_ids if i in by_id]
    if not chain:
        return {}
    a, b = nodes[chain[0].node_start], nodes[chain[0].node_end]
    d = [b[k] - a[k] for k in range(3)]
    length = math.sqrt(sum(c * c for c in d)) or 1.0
    d = [c / length for c in d]

    def t(p):
        return sum((p[k] - a[k]) * d[k] for k in range(3))

    spans = {}
    for member in chain:
        s, e = t(nodes[member.node_start]), t(nodes[member.node_end])
        spans[member.id] = (min(s, e), max(s, e), s > e)
    lo = min(s for s, _, _ in spans.values())
    hi = max(e for _, e, _ in spans.values())
    total = (hi - lo) or 1.0
    return {i: ((s - lo) / total, (e - lo) / total, flipped) for i, (s, e, flipped) in spans.items()}


def split_range(ranges, start, end):
    """Map an element-relative range onto its members: [(id, a, b), ...].

    `a`, `b` are relative to each member, in the member's own direction. A
    member wholly inside gets 0..1, members outside are left out.
    """
    out = []
    for member_id, (t0, t1, flipped) in ranges.items():
        lo, hi = max(start, t0), min(end, t1)
        if hi - lo <= 1e-9:
            continue
        span = (t1 - t0) or 1.0
        a, b = (lo - t0) / span, (hi - t0) / span
        if flipped:
            a, b = 1.0 - b, 1.0 - a
        a = 0.0 if a < 1e-9 else a
        b = 1.0 if b > 1.0 - 1e-9 else b
        out.append((member_id, a, b))
    return out
