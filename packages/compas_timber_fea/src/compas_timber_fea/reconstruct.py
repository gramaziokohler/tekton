"""Rebuild a TimberModel from a StructuralModel.

The translation Timber -> Structural throws away the joints' *types* and the
beams' features, but not their bodies: every beam member carries its source
GUID, its segments chain along the beam's system line, the section holds
width and height and the orientation vector is the section's Y axis. That is
everything `Beam.from_centerline` asks for. So a StructuralModel that arrives
on its own - loaded from JSON, handed back by an engineer, straight out of the
worker - can become a TimberModel again, results included.

What comes back, and what does not:

- **Beams**: one per ``source_element_id``, centreline from the first segment
  start to the last segment end, section and orientation restored, GUID
  restored so `attach_results_to_timber` finds them.
- **Plates**: one per ``source_element_id`` when the plate was pushed as a
  single surface; subdivided plates are reported and skipped (merging the
  patches back into one outline is not done here).
- **Joints**: not rebuilt. The neutral model knows that two beams are
  connected (the connector members) and which joint GUID the connector came
  from, but not the joint class - a butt is not a lap. Connectivity is
  returned separately for anyone who wants to act on it.

One caveat on the geometry: the system line is the *effective* centreline,
which includes the blank extensions the structural graph adds (up to 30 cm
per end). The rebuilt beam is therefore the blank, not the trimmed piece.
"""

from uuid import UUID

from compas.geometry import Frame
from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Polyline
from compas.geometry import Vector
from compas.geometry import cross_vectors

from compas_timber_fea.core.units import scale_to_meters
from compas_timber_fea.results import attach_results_to_timber
from compas_timber_fea.results import chain_endpoints


def structural_to_timber(structural_model, attach_results=True):
    """Rebuild a TimberModel from ``structural_model``.

    Parameters
    ----------
    structural_model : StructuralModel
    attach_results : bool
        When the structural model carries results, write them onto the
        rebuilt beams as ``beam.attributes["analysis"]``.

    Returns
    -------
    tuple
        ``(timber_model, report)`` - the model, and a list of strings saying
        what was rebuilt and what was skipped.
    """
    from compas_timber.model import TimberModel

    scale = 1.0 / scale_to_meters(structural_model.source_units)
    model = TimberModel()
    report = []

    beams = rebuild_beams(structural_model, scale)
    for beam in beams:
        model.add_element(beam)
    report.append(f"{len(beams)} beams rebuilt")

    plates, skipped = rebuild_plates(structural_model, scale)
    for plate in plates:
        model.add_element(plate)
    if plates:
        report.append(f"{len(plates)} plates rebuilt")
    for guid, count in skipped:
        report.append(f"plate {guid[:8]} skipped: {count} surfaces, merging patches is not implemented")

    connections = beam_connectivity(structural_model)
    if connections:
        report.append(f"{len(connections)} beam-to-beam connections known, joint types are not (not rebuilt)")

    if attach_results and structural_model.results:
        attached = attach_results_to_timber(structural_model, model)
        report.append(f"results attached to {len(attached)} of {len(beams)} beams")

    return model, report


def rebuild_beams(structural_model, scale=1.0):
    """Beams from the BEAM members, one per source element, in source units."""
    from compas_timber.elements import Beam

    points = {node.id: node.point for node in structural_model.nodes}
    sections = {section.id: section for section in structural_model.sections}

    grouped = {}
    for member in structural_model.members:
        if member.member_type == "BEAM" and member.source_element_id:
            grouped.setdefault(member.source_element_id, []).append(member)

    beams = []
    for source_id, members in grouped.items():
        start_id, end_id = chain_endpoints(members)
        start = points[start_id]
        end = points[end_id]
        centerline = Line(_scaled(start, scale), _scaled(end, scale))

        section = sections.get(members[0].section_id)
        width = (section.width if section else 0.0) * scale
        height = (section.height if section else 0.0) * scale

        # The orientation vector is the section's Y axis; Beam wants Z.
        # from_centerline derives y = -(x × z), so z = x × y closes the triad.
        x = centerline.vector
        y = Vector(*members[0].orientation_vector)
        z = Vector(*cross_vectors(x, y))
        beam = Beam.from_centerline(centerline, width, height, z_vector=z if z.length > 1e-9 else None)
        _restore_guid(beam, source_id)
        beam.attributes["source_element_id"] = source_id
        beams.append(beam)
    return beams


def rebuild_plates(structural_model, scale=1.0):
    """Plates from surfaces that map 1:1 onto a source plate; returns (plates, skipped)."""
    from compas_timber.elements import Plate

    points = {node.id: node.point for node in structural_model.nodes}
    thicknesses = {t.id: t for t in structural_model.thicknesses}

    grouped = {}
    for surface in structural_model.surfaces:
        key = surface.source_element_id or f"surface-{surface.id}"
        grouped.setdefault(key, []).append(surface)

    plates = []
    skipped = []
    for source_id, surfaces in grouped.items():
        if len(surfaces) != 1:
            skipped.append((source_id, len(surfaces)))
            continue
        surface = surfaces[0]
        thickness = thicknesses.get(surface.thickness_id)
        t = (thickness.thickness if thickness else 0.0) * scale
        outline = [_scaled(points[n], scale) for n in surface.nodes]
        if len(outline) < 3:
            skipped.append((source_id, 0))
            continue
        normal = _polygon_normal(outline)
        half = normal * (t / 2.0)
        outline_a = Polyline([Point(*(p - half)) for p in outline] + [Point(*(outline[0] - half))])
        outline_b = Polyline([Point(*(p + half)) for p in outline] + [Point(*(outline[0] + half))])
        plate = Plate.from_outlines(outline_a, outline_b)
        _restore_guid(plate, source_id)
        plate.attributes["source_element_id"] = source_id
        plates.append(plate)
    return plates, skipped


def beam_connectivity(structural_model):
    """[(beam guid a, beam guid b, joint guid or None)] from the connector members."""
    beam_of_node = {}
    for member in structural_model.members:
        if member.member_type == "BEAM" and member.source_element_id:
            beam_of_node[member.node_start] = member.source_element_id
            beam_of_node[member.node_end] = member.source_element_id

    seen = set()
    connections = []
    for member in structural_model.members:
        if member.source_element_type != "connector":
            continue
        a = beam_of_node.get(member.node_start)
        b = beam_of_node.get(member.node_end)
        if a is None or b is None or a == b:
            continue
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        connections.append((a, b, member.source_joint_start))
    return connections


def _scaled(point, scale):
    return Point(point[0] * scale, point[1] * scale, point[2] * scale)


def _restore_guid(element, source_id):
    """Give the element its original GUID back, so results and references still match."""
    try:
        element._guid = UUID(str(source_id))
    except (ValueError, AttributeError, TypeError):
        pass


def _polygon_normal(points):
    """Newell's method - robust for any planar polygon, convex or not."""
    nx = ny = nz = 0.0
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    normal = Vector(nx, ny, nz)
    return normal.unitized() if normal.length > 1e-12 else Vector(0, 0, 1)


__all__ = [
    "structural_to_timber",
    "rebuild_beams",
    "rebuild_plates",
    "beam_connectivity",
    "chain_endpoints",
]
