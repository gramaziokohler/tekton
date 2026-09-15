"""Deformed shapes and result colouring, pure COMPAS.

Everything here is geometry arithmetic on the neutral model: no Rhino, no
Grasshopper, so it runs in the repo venv under pytest as well as inside
Rhino's CPython. The component (`tekton_visualize`) only converts the
returned points, faces and colours into Rhino types.

Two ideas carry the module:

- A **station** is a point along a member where RFEM reported a value. The
  reader stores them as `StructuralMemberResult` rows with a 0..1 position and,
  since the deformation tables are read, a global displacement vector. A
  member without result rows still has its two nodes, whose displacements are
  interpolated linearly - enough for a straight member under a rigid-body
  move, wrong for a beam bending between them, which is why the member table
  is read at all.
- The **section mesh** sweeps the rectangular cross-section along the deformed
  stations. Width lies along the member's orientation vector (the segment
  frame's Y axis), height along the third axis. Colour is per station, so the
  mesh shows the run of the quantity along the member, not one flat colour.
"""

from compas.geometry import Point
from compas.geometry import Vector
from compas.geometry import cross_vectors
from compas.geometry import normalize_vector

#: Result quantity name -> function(StructuralMemberResult) -> float.
QUANTITIES = {
    "displacement": lambda row: row.displacement.length if row.displacement is not None else 0.0,
    "N": lambda row: row.axial,
    "Vy": lambda row: row.shear_y,
    "Vz": lambda row: row.shear_z,
    "Mt": lambda row: row.torsion,
    "My": lambda row: row.moment_y,
    "Mz": lambda row: row.moment_z,
    "utilization": lambda row: float((row.metadata or {}).get("utilization", 0.0) or 0.0),
}

#: Whether the quantity is drawn by its absolute value (forces alternate in sign).
SIGNED = {"N", "Vy", "Vz", "Mt", "My", "Mz"}

#: Surface quantities: name -> function(StructuralSurfaceResult) -> float.
#: Membrane forces in kN/m, moments in kNm/m, shear from the sample metadata.
SURFACE_QUANTITIES = {
    "displacement": lambda r: r.displacement.length if r.displacement is not None else 0.0,
    "n_x": lambda r: r.membrane_force_x,
    "n_y": lambda r: r.membrane_force_y,
    "n_xy": lambda r: r.membrane_force_xy,
    "m_x": lambda r: r.moment_x,
    "m_y": lambda r: r.moment_y,
    "m_xy": lambda r: r.moment_xy,
    "v_x": lambda r: float((r.metadata or {}).get("v_x", 0.0) or 0.0),
    "v_y": lambda r: float((r.metadata or {}).get("v_y", 0.0) or 0.0),
}


def quantity_of(row, quantity):
    """Value of ``quantity`` on one result row; forces by absolute value."""
    getter = QUANTITIES.get(quantity or "displacement", QUANTITIES["displacement"])
    value = getter(row) or 0.0
    return abs(value) if quantity in SIGNED else value


def surface_quantity_of(sample, quantity):
    """Value of ``quantity`` on one surface sample; forces by absolute value. Unknown -> 0."""
    getter = SURFACE_QUANTITIES.get(quantity or "displacement")
    if getter is None:
        return 0.0
    value = getter(sample) or 0.0
    return abs(value) if quantity != "displacement" else value


def surface_outline(structural_model, surface):
    """The surface's corner points, in model units."""
    points = {n.id: n.point for n in structural_model.nodes}
    outline = [points.get(n) for n in surface.nodes]
    return [] if any(p is None for p in outline) else outline


def surface_stations(structural_model, result_set, surface, quantity="displacement"):
    """Sample points of a surface: the result mesh nodes when read, else the corners.

    Each station carries the point, its displacement and the value of
    ``quantity``, so the caller can draw a deformed, coloured mesh. Without
    surface results the corners move with the nodal deformations, which is
    enough to see the plate go along with its neighbours, not to see it bend.
    """
    node_results = (result_set.node_results or {}) if result_set else {}
    samples = ((result_set.surface_results or {}).get(surface.id) or []) if result_set else []
    stations = []
    for sample in samples:
        if sample.position is None:
            continue
        stations.append(Station(0.0, Point(*sample.position), sample.displacement, surface_quantity_of(sample, quantity)))
    if stations:
        return stations
    corners = surface_corner_stations(structural_model, result_set, surface)
    if quantity != "displacement":
        for station in corners:
            station.value = 0.0
    return corners


def surface_corner_stations(structural_model, result_set, surface):
    """The surface's corners with their nodal displacements - the deformed outline."""
    node_results = (result_set.node_results or {}) if result_set else {}
    stations = []
    for node_id, point in zip(surface.nodes, surface_outline(structural_model, surface)):
        result = node_results.get(node_id)
        displacement = Vector(*result.displacement) if result is not None and result.displacement is not None else Vector(0, 0, 0)
        stations.append(Station(0.0, point, displacement, displacement.length))
    return stations


def colour_rgb(value, low=0.0, high=1.0):
    """Value -> (r, g, b) on a green -> yellow -> red ramp.

    Beyond ``high`` the ramp does not keep interpolating but goes hard red: an
    exceedance should catch the eye, not fade out gently.
    """
    if high <= low:
        t = 0.0
    else:
        t = (float(value) - low) / (high - low)

    if t <= 0.0:
        return (40, 160, 60)
    if t >= 1.0:
        return (200, 30, 30)

    if t < 0.5:
        k = t / 0.5
        return (int(40 + (240 - 40) * k), int(160 + (200 - 160) * k), int(60 + (40 - 60) * k))
    k = (t - 0.5) / 0.5
    return (int(240 + (200 - 240) * k), int(200 + (30 - 200) * k), int(40 + (30 - 40) * k))


class Station(object):
    """One sample point along a member: parameter, undeformed point, displacement, value."""

    __slots__ = ("t", "point", "displacement", "value")

    def __init__(self, t, point, displacement, value):
        self.t = t
        self.point = point
        self.displacement = displacement
        self.value = value

    def deformed(self, exaggeration=1.0, scale=1.0):
        """Deformed point: (point + displacement * exaggeration) * scale.

        ``scale`` takes the model (metres) into document units; the
        exaggeration applies before that, so it is unit-free.
        """
        d = self.displacement or Vector(0, 0, 0)
        return Point(
            (self.point.x + d.x * exaggeration) * scale,
            (self.point.y + d.y * exaggeration) * scale,
            (self.point.z + d.z * exaggeration) * scale,
        )


def member_stations(structural_model, result_set, member, quantity="displacement"):
    """Stations along ``member`` from its result rows, or from its two nodes.

    Rows carry the value of ``quantity``; rows without a displacement fall
    back to the linear interpolation of the node displacements, so a member
    whose deformation table was not read still moves with its nodes.
    """
    nodes = {node.id: node.point for node in structural_model.nodes}
    start = nodes.get(member.node_start)
    end = nodes.get(member.node_end)
    if start is None or end is None:
        return []

    node_results = (result_set.node_results or {}) if result_set else {}
    d_start = _node_displacement(node_results, member.node_start)
    d_end = _node_displacement(node_results, member.node_end)

    def interpolated(t):
        return Vector(
            d_start.x + (d_end.x - d_start.x) * t,
            d_start.y + (d_end.y - d_start.y) * t,
            d_start.z + (d_end.z - d_start.z) * t,
        )

    def point_at(t):
        return Point(start.x + (end.x - start.x) * t, start.y + (end.y - start.y) * t, start.z + (end.z - start.z) * t)

    rows = sorted(((result_set.member_results or {}).get(member.id) or []) if result_set else [], key=lambda r: r.position)
    stations = []
    for row in rows:
        t = min(max(float(row.position), 0.0), 1.0)
        displacement = row.displacement if row.displacement is not None else interpolated(t)
        stations.append(Station(t, point_at(t), displacement, quantity_of(row, quantity)))

    # Ends must exist for the shape to be closed and for members without rows.
    if not stations or stations[0].t > 1e-6:
        stations.insert(0, Station(0.0, start, d_start, stations[0].value if stations else 0.0))
    if stations[-1].t < 1.0 - 1e-6:
        stations.append(Station(1.0, end, d_end, stations[-1].value))
    return stations


def _node_displacement(node_results, node_id):
    result = node_results.get(node_id)
    if result is None or result.displacement is None:
        return Vector(0, 0, 0)
    return Vector(*result.displacement)


def deformed_polyline(stations, exaggeration=1.0, scale=1.0):
    """The stations' deformed points, in order - one polyline per member."""
    return [station.deformed(exaggeration, scale) for station in stations]


def section_frames(points, orientation):
    """Local (y, z) axes at every point of a polyline.

    y follows ``orientation`` made orthogonal to the local tangent, z closes
    the right-handed triad. A tangent parallel to the orientation (degenerate
    input) falls back to the global axis least aligned with it.
    """
    n = len(points)
    frames = []
    orientation = normalize_vector(list(orientation)) if _length(orientation) > 1e-12 else [0.0, 0.0, 1.0]
    for i in range(n):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, n - 1)]
        tangent = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
        if _length(tangent) < 1e-12:
            tangent = [1.0, 0.0, 0.0]
        tangent = normalize_vector(tangent)

        y = _orthogonalize(orientation, tangent)
        if _length(y) < 1e-9:
            fallback = min(([1, 0, 0], [0, 1, 0], [0, 0, 1]), key=lambda axis: abs(_dot(axis, tangent)))
            y = _orthogonalize(fallback, tangent)
        y = normalize_vector(y)
        z = normalize_vector(cross_vectors(tangent, y))
        frames.append((y, z))
    return frames


def section_mesh(points, width, height, orientation, values=None, low=0.0, high=1.0):
    """Sweep a ``width`` x ``height`` rectangle along ``points``.

    Returns ``(vertices, faces, colours)``: vertices as (x, y, z) tuples, four
    per station; faces as index lists (quads); one (r, g, b) per vertex from
    the station's value. Both end caps are closed.
    """
    n = len(points)
    if n < 2:
        return [], [], []
    frames = section_frames(points, orientation)
    values = list(values) if values is not None else [0.0] * n
    hw, hh = width / 2.0, height / 2.0

    vertices = []
    colours = []
    for i, point in enumerate(points):
        y, z = frames[i]
        colour = colour_rgb(values[i] if i < len(values) else 0.0, low, high)
        for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vertices.append((
                point[0] + y[0] * hw * sy + z[0] * hh * sz,
                point[1] + y[1] * hw * sy + z[1] * hh * sz,
                point[2] + y[2] * hw * sy + z[2] * hh * sz,
            ))
            colours.append(colour)

    faces = []
    for i in range(n - 1):
        a = i * 4
        b = a + 4
        for k in range(4):
            faces.append([a + k, a + (k + 1) % 4, b + (k + 1) % 4, b + k])
    faces.append([3, 2, 1, 0])
    last = (n - 1) * 4
    faces.append([last, last + 1, last + 2, last + 3])
    return vertices, faces, colours


def _length(v):
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _orthogonalize(v, unit):
    d = _dot(v, unit)
    return [v[0] - unit[0] * d, v[1] - unit[1] * d, v[2] - unit[2] * d]


__all__ = [
    "QUANTITIES",
    "SURFACE_QUANTITIES",
    "Station",
    "surface_quantity_of",
    "surface_outline",
    "surface_stations",
    "surface_corner_stations",
    "colour_rgb",
    "quantity_of",
    "member_stations",
    "deformed_polyline",
    "section_frames",
    "section_mesh",
]
