"""Deformed shapes and section meshes, offline.

tekton_gh is the Rhino-side package and not installed into the repo venv (it
targets Rhino's CPython 3.9), so its pure module is put on the path here.
"""

import os
import re
import sys

import pytest
from compas.geometry import Point
from compas.geometry import Vector

from tekton_core.core.model import StructuralMember
from tekton_core.core.model import StructuralMemberResult
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralNodeResult
from tekton_core.core.model import StructuralResultSet

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "tekton_gh", "src"))

from tekton_gh.visualize import colour_rgb  # noqa: E402
from tekton_gh.visualize import deformed_polyline  # noqa: E402
from tekton_gh.visualize import member_stations  # noqa: E402
from tekton_gh.visualize import quantity_of  # noqa: E402
from tekton_gh.visualize import section_frames  # noqa: E402
from tekton_gh.visualize import section_mesh  # noqa: E402


@pytest.fixture
def beam_model():
    """One 2 m member along X with a 0.1 x 0.2 section."""
    model = StructuralModel()
    model.nodes = [StructuralNode(id=1, point=Point(0, 0, 0)), StructuralNode(id=2, point=Point(2, 0, 0))]
    model.members = [StructuralMember(id=1, node_start=1, node_end=2, section_id=1, orientation_vector=Vector(0, 1, 0))]
    return model


def test_stations_from_member_rows_carry_displacement_and_value(beam_model):
    rows = [
        StructuralMemberResult(member_id=1, load_case_id=1, position=0.0, moment_y=0.0, displacement=Vector(0, 0, 0)),
        StructuralMemberResult(member_id=1, load_case_id=1, position=0.5, moment_y=-3.0, displacement=Vector(0, 0, -0.01)),
        StructuralMemberResult(member_id=1, load_case_id=1, position=1.0, moment_y=0.0, displacement=Vector(0, 0, 0)),
    ]
    result_set = StructuralResultSet(load_case_id=1, member_results={1: rows})

    stations = member_stations(beam_model, result_set, beam_model.members[0], quantity="My")

    assert [s.t for s in stations] == [0.0, 0.5, 1.0]
    assert stations[1].point == Point(1, 0, 0)
    assert stations[1].value == 3.0  # forces by absolute value
    assert stations[1].displacement.z == -0.01


def test_stations_fall_back_to_node_displacements(beam_model):
    """No member table read: the member still moves with its nodes."""
    result_set = StructuralResultSet(
        load_case_id=1,
        node_results={2: StructuralNodeResult(node_id=2, load_case_id=1, displacement=Vector(0, 0, -0.02))},
    )

    stations = member_stations(beam_model, result_set, beam_model.members[0])

    assert len(stations) == 2
    assert stations[0].displacement.z == 0.0
    assert stations[1].displacement.z == -0.02


def test_deformed_polyline_applies_exaggeration_then_units(beam_model):
    result_set = StructuralResultSet(
        load_case_id=1,
        node_results={2: StructuralNodeResult(node_id=2, load_case_id=1, displacement=Vector(0, 0, -0.02))},
    )
    stations = member_stations(beam_model, result_set, beam_model.members[0])

    points = deformed_polyline(stations, exaggeration=10.0, scale=1000.0)

    assert points[1] == Point(2000.0, 0.0, -200.0)  # 2 m -> mm, 0.02 m * 10 -> mm


def test_section_frames_follow_the_orientation_vector():
    (y, z), = section_frames([Point(0, 0, 0), Point(1, 0, 0)], Vector(0, 1, 0))[:1]

    assert [round(c, 9) for c in y] == [0, 1, 0]
    assert [round(c, 9) for c in z] == [0, 0, 1]


def test_section_frames_survive_orientation_parallel_to_tangent():
    frames = section_frames([Point(0, 0, 0), Point(0, 0, 1)], Vector(0, 0, 1))

    y, z = frames[0]
    assert abs(y[2]) < 1e-9 and abs(z[2]) < 1e-9  # both perpendicular to the tangent


def test_section_mesh_is_a_closed_quad_sweep():
    points = [Point(0, 0, 0), Point(1, 0, 0), Point(2, 0, 0)]

    vertices, faces, colours = section_mesh(points, width=0.1, height=0.2, orientation=Vector(0, 1, 0), values=[0, 1, 0], low=0, high=1)

    assert len(vertices) == 12
    assert len(faces) == 4 * 2 + 2
    assert all(len(face) == 4 for face in faces)
    assert len(colours) == 12
    assert colours[4] == (200, 30, 30)  # middle station at the upper bound: hard red
    ys = sorted(set(round(v[1], 6) for v in vertices))
    zs = sorted(set(round(v[2], 6) for v in vertices))
    assert ys == [-0.05, 0.05] and zs == [-0.1, 0.1]


def test_colour_ramp_clamps_beyond_bounds():
    assert colour_rgb(-1.0) == (40, 160, 60)
    assert colour_rgb(0.5, 0.0, 1.0) == (240, 200, 40)
    assert colour_rgb(2.0) == (200, 30, 30)


def test_quantity_lookup_defaults_to_displacement():
    row = StructuralMemberResult(member_id=1, load_case_id=1, axial=-4.0, displacement=Vector(0, 0, -0.003))

    assert quantity_of(row, None) == pytest.approx(0.003)
    assert quantity_of(row, "N") == 4.0
    assert quantity_of(row, "utilization") == 0.0


def test_surface_stations_use_result_samples_or_fall_back_to_corners():
    from tekton_core.core.model import StructuralSurface, StructuralSurfaceResult
    from tekton_gh.visualize import surface_stations

    model = StructuralModel()
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in ((1, (0, 0, 0)), (2, (2, 0, 0)), (3, (2, 1, 0)), (4, (0, 1, 0)))]
    surface = StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)
    model.surfaces = [surface]

    corners = surface_stations(model, StructuralResultSet(load_case_id=1, node_results={3: StructuralNodeResult(node_id=3, load_case_id=1, displacement=Vector(0, 0, -0.01))}), surface)
    assert len(corners) == 4 and corners[2].displacement.z == -0.01

    sample = StructuralSurfaceResult(surface_id=1, load_case_id=1, position=Point(1, 0.5, 0), displacement=Vector(0, 0, -0.02), moment_x=-1.5)
    result_set = StructuralResultSet(load_case_id=1, surface_results={1: [sample]})
    samples = surface_stations(model, result_set, surface, quantity="m_x")
    assert len(samples) == 1 and samples[0].value == 1.5 and samples[0].point == Point(1, 0.5, 0)


def neutral_plate_model():
    """A single 4x4 m plate in the neutral model, thick enough to mesh."""
    from compas.geometry import Point as _P

    from tekton_core.core.model import StructuralModel
    from tekton_core.core.model import StructuralNode
    from tekton_core.core.model import StructuralSurface
    from tekton_core.core.model import StructuralThickness

    from tekton_core.core.materials import Material

    corners = {1: (0, 0, 0), 2: (4, 0, 0), 3: (4, 4, 0), 4: (0, 4, 0)}
    model = StructuralModel()
    model.nodes = [StructuralNode(id=i, point=_P(*p)) for i, p in corners.items()]
    model.materials[1] = Material.resolve("C24")
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.2)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)]
    model.load_cases.append(_self_weight_case())
    return model, corners


def _self_weight_case():
    from tekton_core.core.model import StructuralLoadCase

    return StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True)


def test_surface_meshes_are_constrained_by_their_outline():
    """A concave plate must not be drawn as its convex hull.

    `Mesh.CreateFromTessellation` triangulates a *cloud of points*: without
    the outline in its `edges` argument it returns the convex hull, so a
    plate whose boundary steps inwards is drawn with the notch filled in - a
    spike straight across the outline. On the faceted hypar example 38 of 46
    facets are concave and were drawn up to 40% too large.

    The call needs Rhino, so this guards the source instead: the component
    must never tessellate without handing over the boundary, and must not
    fall back to a triangle fan from corner 0 (which spills outside a
    concave outline just the same).
    """
    path = os.path.join(os.path.dirname(__file__), "..", "..", "packages",
                        "tekton_gh", "components", "tekton_visualize", "code.py")
    with open(path) as handle:
        source = handle.read()

    assert "CreateFromTessellation" in source, "the surface mesh path moved - update this test"
    for call in re.findall(r"CreateFromTessellation\(([^)]*)\)", source):
        edges = call.split(",")[1].strip()
        assert edges != "None", "tessellating without the outline returns the convex hull"
        assert edges.startswith("["), "the outline must be passed as the edges argument"


def test_the_solved_mesh_travels_with_the_results():
    """The plate mesh must survive the trip back, or the viewer guesses.

    Re-triangulating the sample points is a 2D Delaunay of a projected
    cloud; on a trimmed or concave plate that produces slivers and zero-area
    triangles. Measured on the faceted hypar: 156 degenerate triangles of
    1058 and 18% below quality 0.3, where the gmsh mesh those same points
    came from has none. So the connectivity rides along in the result set's
    metadata, keyed by surface id, as triples of the samples' `node_tag`.
    """
    import math

    from tekton_opensees.runner import run_model
    from tekton_core.core.model import StructuralSupport
    from tekton_core.core.support_types import key_from_name
    from tekton_core.core.support_types import stiffnesses

    model, _ = neutral_plate_model()
    model.supports.append(
        StructuralSupport(id=1, nodes=[n.id for n in model.nodes],
                          name="all", **stiffnesses(key_from_name("pinned"))))
    run_model(model, mesh_target_length=1.0)

    result_set = list(model.results.values())[0]
    triangles = (result_set.metadata or {}).get("surface_triangles") or {}
    assert triangles, "the solved mesh did not come back with the results"

    surface_id = sorted(triangles)[0]
    samples = {s.metadata.get("node_tag"): s.position
               for s in result_set.surface_results[int(surface_id)]}
    qualities = []
    for triangle in triangles[surface_id]:
        corners = [samples.get(int(t)) for t in triangle]
        assert all(c is not None for c in corners), "a triangle names an unknown node tag"
        a, b, c = (math.dist(tuple(corners[i])[:3], tuple(corners[(i + 1) % 3])[:3])
                   for i in range(3))
        s = (a + b + c) / 2
        area_sq = s * (s - a) * (s - b) * (s - c)
        qualities.append(0.0 if area_sq <= 0 or a * b * c == 0
                         else 8 * (s - a) * (s - b) * (s - c) / (a * b * c))

    # gmsh does not emit degenerate triangles; if these are slivers we are
    # looking at a re-triangulation again.
    assert min(qualities) > 0.3, "the carried mesh contains slivers - not the solved one"


def test_the_display_caps_a_concave_plate_without_a_fan():
    """A solid plate preview must not fan its end caps from corner 0.

    `TektonDisplay` builds each plate as a box: the outline extruded by
    +-t/2, sides as quads, and the two caps. Fanning the caps from corner 0
    only works while the outline is convex; a faceted shell is full of
    plates that step inwards (38 of 46 on the hypar example) and there the
    fan spills across the notch - every one of those 38 came out with the
    wrong cap area. Triangulating the outline instead fixes all of them.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "..", "packages",
                        "tekton_gh", "components", "tekton_display", "code.py")
    with open(path) as handle:
        source = handle.read()

    assert "CreateFromClosedPolyline" in source, (
        "the slab cap no longer triangulates its outline - a fan from corner 0 "
        "spills outside a concave plate")
    fan = source.count("m.Faces.AddFace(0, i + 1, i)")
    assert fan <= 1, "the corner-0 fan should survive only as the fallback"
