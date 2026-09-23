"""Plate outlines -> conforming triangle meshes, for OpenSees only.

OpenSees has no mesher. RFEM does, which is why the neutral model carries no
mesh at all: a ``StructuralSurface`` is a polygon of node ids, and the plate
design study is explicit that subdivision upstream destroys plate identity
and with it the mapping of results back to the plate. Tessellation is
allowed in exactly one place - inside a backend adapter that needs a mesh.
This is that place, and the mesh never leaves it.

**Conformity is the whole problem.** Two plates sharing an edge must end up
with identical nodes on it; otherwise they are not connected, and OpenSees
solves a model with a crack in it and reports plausible nonsense. Meshing
each plate independently does not give that, not even with identical input
vertices: measured on two 4x3 plates, ``compas_cgal``'s refiner split the
shared edge 8 against 10 at a 0.5 m target, because it adds boundary nodes
of its own accord (see ``tests/spike_meshers.py``).

gmsh can be told otherwise. ``setTransfiniteCurve`` prescribes how many
nodes a curve gets, so a shared edge is subdivided identically from both
sides by construction rather than by luck. That is what
:func:`mesh_surfaces` does: it meshes the whole assembly in one gmsh model,
with shared edges as shared curve objects, so conformity is not even a
question - the plates literally reference the same geometry.

gmsh keeps global state and is not re-entrant. Every entry point here
initialises and finalises around its own work, in a ``finally``; the runner
already gives each solve its own process.
"""

import math

#: Nodes generated for a plate mesh start here, so they never collide with
#: the neutral node ids (which the outline vertices keep).
MESH_TAG_BASE = 2_000_000

#: Default target edge length in metres. Comparable to RFEM's default target
#: FE length (~0.5 m); a mesh hint, never part of the neutral model.
DEFAULT_TARGET_LENGTH = 0.5

#: Two outline vertices closer than this are the same point.
TOLERANCE = 1e-7

#: Refuse to mesh beyond this many triangles. A plate model that asks for more
#: is almost always a unit error - a millimetre model declared as metres makes
#: a 3 m edge 3000 units long, and gmsh then tries to put 6000 segments on it
#: and disappears into the C++ layer where a Python timeout cannot reach it.
#: Failing loudly beats a hang that looks like a crash.
MAX_TRIANGLES = 200_000


class MeshedSurface:
    """One plate, meshed. ``nodes`` maps a mesh tag to its point."""

    def __init__(self, surface_id, source_element_id=None):
        self.surface_id = surface_id
        self.source_element_id = source_element_id
        self.node_tags = []        # every node of this plate, outline first
        self.triangles = []        # (tag, tag, tag), counter-clockwise
        self.outline_tags = []     # the neutral node ids on the outline
        self.area = 0.0            # m2, for load and self-weight distribution


class MeshResult:
    """What the builder needs after meshing the whole assembly."""

    def __init__(self):
        self.surfaces = {}         # surface id -> MeshedSurface
        self.points = {}           # node tag -> (x, y, z), mesh nodes only
        self.warnings = []

    @property
    def node_count(self):
        return len(self.points)

    @property
    def triangle_count(self):
        return sum(len(surface.triangles) for surface in self.surfaces.values())


def _distance(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _edge_key(a, b):
    """Undirected edge between two neutral node ids."""
    return (a, b) if a <= b else (b, a)


def shared_edges(surfaces):
    """Edges used by more than one surface, as ``{(id, id): [surface ids]}``.

    The neutral model expresses adjacency by two plates naming the same node
    ids, so an edge is shared exactly when it appears in two outlines. This
    is the BorderChain in the form the model actually carries today; once
    real BorderChain objects exist, they replace this derivation and bring
    partial contact with them.
    """
    seen = {}
    for surface in surfaces:
        nodes = list(surface.nodes)
        for a, b in zip(nodes, nodes[1:] + nodes[:1]):
            if a == b:
                continue
            seen.setdefault(_edge_key(a, b), []).append(surface.id)
    return {edge: owners for edge, owners in seen.items() if len(owners) > 1}


def subdivisions_for(length, target_length):
    """How many segments an edge of this length gets. At least one."""
    if target_length <= 0:
        return 1
    return max(1, int(math.ceil(length / target_length - 1e-9)))


def mesh_surfaces(model, target_length=DEFAULT_TARGET_LENGTH):
    """Mesh every surface of the model in one gmsh model.

    All plates are built into a single gmsh geometry, so an edge shared by
    two plates is one curve object used by both faces. Conformity along
    shared edges is then guaranteed by the geometry, not by matching two
    independent meshes afterwards.

    Parameters
    ----------
    model : StructuralModel
    target_length : float
        Target edge length in metres - a hint for the free edges; shared
        edges are prescribed from the same value on both sides.

    Returns
    -------
    MeshResult

    Raises
    ------
    RuntimeError
        When gmsh produces no elements for a surface: better a loud failure
        than a plate silently missing from the analysis.
    """
    import gmsh

    result = MeshResult()
    if not getattr(model, "surfaces", None):
        return result

    points = {node.id: (float(node.point.x), float(node.point.y), float(node.point.z))
              for node in model.nodes}
    shared = shared_edges(model.surfaces)
    _refuse_implausible_mesh(model, points, target_length)

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_length * 0.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_length)
        gmsh.model.add("tekton")
        geo = gmsh.model.geo

        point_tags = {}      # neutral node id -> gmsh point tag
        curve_tags = {}      # undirected edge -> gmsh curve tag
        surface_faces = {}   # surface id -> gmsh surface tag

        def ring(node_ids):
            """gmsh curve loop for a closed ring of neutral node ids."""
            loop = []
            ids = list(node_ids)
            for a, b in zip(ids, ids[1:] + ids[:1]):
                if a == b or a not in points or b not in points:
                    continue
                for node_id in (a, b):
                    if node_id not in point_tags:
                        x, y, z = points[node_id]
                        point_tags[node_id] = geo.addPoint(x, y, z, target_length)
                key = _edge_key(a, b)
                if key not in curve_tags:
                    # Always create the curve in key order, so the sign below
                    # describes the traversal direction correctly for both
                    # plates that share it.
                    curve_tags[key] = geo.addLine(point_tags[key[0]], point_tags[key[1]])
                    if key in shared:
                        # The whole point: both plates inherit this subdivision.
                        segments = subdivisions_for(_distance(points[a], points[b]), target_length)
                        geo.mesh.setTransfiniteCurve(curve_tags[key], segments + 1)
                # Sign tells gmsh the direction the loop traverses the curve.
                loop.append(curve_tags[key] if (a, b) == key else -curve_tags[key])
            return loop

        for surface in model.surfaces:
            loop = ring(surface.nodes)
            if len(loop) < 3:
                result.warnings.append(
                    "surface {} has fewer than 3 distinct edges - skipped".format(surface.id))
                continue
            # An opening is a second loop on the same face: gmsh subtracts
            # every loop after the first. The ring has to be closed and lie
            # inside the outline; a degenerate one is reported rather than
            # silently swallowing the plate.
            loops = [geo.addCurveLoop(loop)]
            for index, opening in enumerate(getattr(surface, "openings", None) or []):
                hole = ring(opening)
                if len(hole) < 3:
                    result.warnings.append(
                        "surface {}: opening {} has fewer than 3 distinct edges - ignored".format(
                            surface.id, index))
                    continue
                loops.append(geo.addCurveLoop(hole))
            face = geo.addPlaneSurface(loops)
            surface_faces[surface.id] = face

        geo.synchronize()
        gmsh.model.mesh.generate(2)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        coords = [float(value) for value in coords]
        gmsh_to_tekton = {}
        for index, gmsh_tag in enumerate(node_tags):
            point = (coords[index * 3], coords[index * 3 + 1], coords[index * 3 + 2])
            existing = _matching_neutral_node(point, points)
            if existing is not None:
                gmsh_to_tekton[int(gmsh_tag)] = existing
            else:
                tag = MESH_TAG_BASE + len(result.points)
                gmsh_to_tekton[int(gmsh_tag)] = tag
                result.points[tag] = point

        for surface in model.surfaces:
            face = surface_faces.get(surface.id)
            if face is None:
                continue
            meshed = MeshedSurface(surface.id, getattr(surface, "source_element_id", None))
            meshed.outline_tags = [node_id for node_id in surface.nodes]
            element_types, _, node_lists = gmsh.model.mesh.getElements(2, face)
            triangles = []
            for element_type, nodes in zip(element_types, node_lists):
                if element_type != 2:       # 2 = 3-node triangle
                    continue
                nodes = [int(value) for value in nodes]
                for start in range(0, len(nodes), 3):
                    triangles.append(tuple(gmsh_to_tekton[node] for node in nodes[start:start + 3]))
            if not triangles:
                raise RuntimeError(
                    "gmsh produced no triangles for surface {}. The outline may be "
                    "non-planar or self-intersecting.".format(surface.id))
            meshed.triangles = triangles
            meshed.node_tags = sorted({tag for triangle in triangles for tag in triangle})
            meshed.area = sum(
                _triangle_area(*(_point_of(tag, points, result.points) for tag in triangle))
                for triangle in triangles
            )
            result.surfaces[surface.id] = meshed

        return result
    finally:
        gmsh.finalize()


def _refuse_implausible_mesh(model, points, target_length):
    """Stop before gmsh does, when the mesh would be absurdly large.

    The usual cause is a unit mismatch: a model authored in millimetres but
    translated as metres. Every length is then 1000x too big, the target
    length stays at half a metre, and gmsh is asked for tens of millions of
    triangles - inside C++, where it neither returns nor responds to a
    Python timeout. `core/units.py` calls this out as *the* default failure
    mode of the whole pipeline; this is the same guard, one layer down.
    """
    estimate = 0
    longest = 0.0
    for surface in model.surfaces:
        outline = list(surface.nodes)
        segments = 0
        for a, b in zip(outline, outline[1:] + outline[:1]):
            if a == b or a not in points or b not in points:
                continue
            length = _distance(points[a], points[b])
            longest = max(longest, length)
            segments += subdivisions_for(length, target_length)
        # A closed outline of N boundary segments yields roughly N^2/4 triangles.
        estimate += max(1, (segments * segments) // 4)

    if estimate > MAX_TRIANGLES:
        raise ValueError(
            "Meshing would produce roughly {:,} triangles (limit {:,}). The longest plate "
            "edge is {:,.1f} against a target edge length of {}. That ratio almost always "
            "means the model is in millimetres but was translated as metres - check "
            "'source_units' on the translator. Raise MAX_TRIANGLES only if the geometry "
            "really is that large.".format(estimate, MAX_TRIANGLES, longest, target_length))


def _matching_neutral_node(point, points):
    """The neutral node id at this point, if there is one."""
    for node_id, candidate in points.items():
        if _distance(point, candidate) < TOLERANCE:
            return node_id
    return None


def _point_of(tag, neutral_points, mesh_points):
    return neutral_points.get(tag) or mesh_points[tag]


def _triangle_area(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
