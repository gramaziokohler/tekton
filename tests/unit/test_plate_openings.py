"""Openings in plates: a window is a hole, not a smaller plate.

Openings are first-class - a closed ring of node ids next to the outline -
rather than subtracted into the outline. Every serious target format carries
them that way (RFEM opening object, IFC inner boundary, SAF opening), and
subtracting would destroy the plate's identity and with it the mapping of
results back onto it.
"""

import pytest

from compas.geometry import Point
from compas.geometry import Polyline

from compas_timber.elements import Plate
from compas_timber.model import TimberModel

from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralSurface
from tekton_core.core.model import StructuralThickness
from tekton_core.translator import TimberToStructural
from tekton_opensees.meshing import mesh_surfaces

SIDE = 4.0
THICKNESS = 0.2
HOLE = 1.0


def neutral_plate(openings=None):
    """A 4x4 plate in the neutral model, optionally with a 1x1 hole."""
    points = {1: (0, 0, 0), 2: (SIDE, 0, 0), 3: (SIDE, SIDE, 0), 4: (0, SIDE, 0),
              5: (1.5, 1.5, 0), 6: (2.5, 1.5, 0), 7: (2.5, 2.5, 0), 8: (1.5, 2.5, 0)}
    model = StructuralModel()
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=THICKNESS)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1,
                                        openings=openings if openings is not None else [])]
    return model, points


def timber_plate(with_opening=True):
    """The same plate as a real compas_timber Plate."""
    outline_a = Polyline([Point(0, 0, 0), Point(SIDE, 0, 0), Point(SIDE, SIDE, 0),
                          Point(0, SIDE, 0), Point(0, 0, 0)])
    outline_b = Polyline([Point(0, 0, THICKNESS), Point(SIDE, 0, THICKNESS),
                          Point(SIDE, SIDE, THICKNESS), Point(0, SIDE, THICKNESS),
                          Point(0, 0, THICKNESS)])
    openings = None
    if with_opening:
        openings = [Polyline([Point(1.5, 1.5, 0), Point(2.5, 1.5, 0), Point(2.5, 2.5, 0),
                              Point(1.5, 2.5, 0), Point(1.5, 1.5, 0)])]
    plate = Plate.from_outlines(outline_a, outline_b, openings=openings)
    model = TimberModel()
    model.add_element(plate)
    return model


def covers(triangles, point_of, target):
    """Is the target point covered by any triangle, in plan?"""
    for triangle in triangles:
        (ax, ay), (bx, by), (cx, cy) = [point_of(t)[:2] for t in triangle]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        u = ((by - cy) * (target[0] - cx) + (cx - bx) * (target[1] - cy)) / d
        v = ((cy - ay) * (target[0] - cx) + (ax - cx) * (target[1] - cy)) / d
        if u >= -1e-9 and v >= -1e-9 and u + v <= 1 + 1e-9:
            return True
    return False


# --- the model -----------------------------------------------------------

def test_a_surface_has_no_openings_by_default():
    model, _ = neutral_plate()
    assert model.surfaces[0].openings == []


def test_openings_are_rings_of_node_ids_not_geometry():
    """Same representation as the outline - node ids, so a shared opening
    edge would work exactly like a shared outline edge."""
    model, _ = neutral_plate([[5, 6, 7, 8]])
    assert model.surfaces[0].openings == [[5, 6, 7, 8]]


def test_openings_survive_the_json_round_trip():
    import os
    import tempfile

    from tekton_core.core.serialization import model_from_json
    from tekton_core.core.serialization import model_to_json

    model, _ = neutral_plate([[5, 6, 7, 8]])
    path = os.path.join(tempfile.mkdtemp(), "m.json")
    model_to_json(model, path)
    assert model_from_json(path).surfaces[0].openings == [[5, 6, 7, 8]]


# --- the mesh ------------------------------------------------------------

def test_the_opening_is_cut_out_of_the_mesh():
    model, points = neutral_plate([[5, 6, 7, 8]])
    result = mesh_surfaces(model, 0.5)
    meshed = result.surfaces[1]

    def point_of(tag):
        return points.get(tag) or result.points[tag]

    assert not covers(meshed.triangles, point_of, (2.0, 2.0))


def test_the_area_is_the_outline_minus_the_opening():
    model, _ = neutral_plate([[5, 6, 7, 8]])
    area = mesh_surfaces(model, 0.5).surfaces[1].area
    assert area == pytest.approx(SIDE * SIDE - HOLE * HOLE, rel=1e-9)


@pytest.mark.parametrize("target", [0.5, 0.25, 0.1])
def test_the_area_is_exact_at_every_mesh_density(target):
    """A polygonal hole has no curvature to approximate - refining must not
    change the area, or something is being smoothed that should not be."""
    model, _ = neutral_plate([[5, 6, 7, 8]])
    assert mesh_surfaces(model, target).surfaces[1].area == pytest.approx(15.0, rel=1e-9)


def test_without_the_opening_the_full_area_is_meshed():
    model, _ = neutral_plate()
    assert mesh_surfaces(model, 0.5).surfaces[1].area == pytest.approx(16.0, rel=1e-9)


def test_a_degenerate_opening_is_reported_not_silently_dropped():
    model, _ = neutral_plate([[5, 6]])          # two points is not a ring
    result = mesh_surfaces(model, 0.5)
    assert result.surfaces[1].area == pytest.approx(16.0, rel=1e-9)
    assert any("opening" in warning for warning in result.warnings)


def test_two_openings_are_both_cut():
    points = {1: (0, 0, 0), 2: (6, 0, 0), 3: (6, 4, 0), 4: (0, 4, 0),
              5: (1, 1, 0), 6: (2, 1, 0), 7: (2, 2, 0), 8: (1, 2, 0),
              9: (4, 1, 0), 10: (5, 1, 0), 11: (5, 2, 0), 12: (4, 2, 0)}
    model = StructuralModel()
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=THICKNESS)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1,
                                        openings=[[5, 6, 7, 8], [9, 10, 11, 12]])]
    assert mesh_surfaces(model, 0.5).surfaces[1].area == pytest.approx(24.0 - 2.0, rel=1e-9)


# --- the translator ------------------------------------------------------

def test_openings_are_read_from_the_timber_plate():
    translator = TimberToStructural(source_units="m")
    structural = translator.translate(timber_plate())
    assert len(structural.surfaces[0].openings) == 1
    assert len(structural.surfaces[0].openings[0]) == 4
    assert any("opening" in line for line in translator.report)


def test_a_plate_without_openings_translates_to_none():
    structural = TimberToStructural(source_units="m").translate(timber_plate(with_opening=False))
    assert structural.surfaces[0].openings == []


def test_the_opening_lands_on_the_mid_surface():
    """The openings live on outline_a; the analysis surface is the middle one.
    Without the t/2 shift the hole sits half a thickness off the plate it is
    meant to cut - and the area comes out wrong rather than failing."""
    structural = TimberToStructural(source_units="m").translate(timber_plate())
    points = {node.id: node.point for node in structural.nodes}
    surface = structural.surfaces[0]
    outline_z = {round(points[i].z, 6) for i in surface.nodes}
    opening_z = {round(points[i].z, 6) for i in surface.openings[0]}
    assert outline_z == opening_z == {THICKNESS / 2}


def test_the_translated_plate_meshes_to_the_right_area():
    structural = TimberToStructural(source_units="m").translate(timber_plate())
    area = mesh_surfaces(structural, 0.5).surfaces[1].area
    assert area == pytest.approx(SIDE * SIDE - HOLE * HOLE, rel=1e-6)


def test_a_plate_built_from_outline_and_thickness_has_no_opening():
    """The outer contour is not a hole, whichever way the outline is wound.

    `Plate.from_outline_thickness` builds the outer contour with
    `interior=False`, but its `tool_position` comes out "right" - that value
    records which side the cutter runs on, relative to the plate's own
    reference side, and for this constructor it is "right" whichever way the
    outline is wound. Reading it as "opening" turned every plate's own
    boundary into a phantom hole: on a 46-facet shell that was 46 spurious
    openings and ~250 junk nodes, and every plate would have been meshed
    with its own outline punched out of it. `counter_sink` is the flag that
    actually separates the two.
    """
    outline = Polyline([Point(0, 0, 0), Point(SIDE, 0, 0), Point(SIDE, SIDE, 0),
                        Point(0, SIDE, 0), Point(0, 0, 0)])
    plate = Plate.from_outline_thickness(outline, THICKNESS)
    # Guard the premise: if compas_timber ever starts tagging the outer
    # contour "left", this test stops proving anything without saying so.
    contours = [f for f in (plate.features or []) if hasattr(f, "tool_position")]
    assert contours, "the plate should carry its outer contour as a feature"
    assert all(not f.counter_sink for f in contours)

    model = TimberModel()
    model.add_element(plate)
    translator = TimberToStructural(source_units="m")
    structural = translator.translate(model)

    assert structural.surfaces[0].openings == []
    assert not any("opening" in line for line in translator.report)
    area = mesh_surfaces(structural, 0.5).surfaces[1].area
    assert area == pytest.approx(SIDE * SIDE, rel=1e-6)
