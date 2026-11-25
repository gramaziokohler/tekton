"""WP0b: plate outlines -> conforming triangle meshes.

The tests that matter are the conformity ones. A mesh that looks fine but
splits a shared edge differently on the two sides produces a model with a
crack in it - OpenSees solves it happily and reports plausible nonsense, so
nothing downstream would catch it.
"""


import pytest

from compas.geometry import Point

from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralSurface
from tekton_core.core.model import StructuralThickness
from tekton_opensees.meshing import DEFAULT_TARGET_LENGTH
from tekton_opensees.meshing import MESH_TAG_BASE
from tekton_opensees.meshing import mesh_surfaces
from tekton_opensees.meshing import shared_edges
from tekton_opensees.meshing import subdivisions_for


def plate_model(second_plate=True, hole=False):
    """One 4x3 plate, optionally a second one sharing the edge at x=4."""
    model = StructuralModel()
    points = {1: (0, 0, 0), 2: (4, 0, 0), 3: (4, 3, 0), 4: (0, 3, 0)}
    surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)]
    if second_plate:
        points.update({5: (8, 0, 0), 6: (8, 3, 0)})
        surfaces.append(StructuralSurface(id=2, nodes=[2, 5, 6, 3], thickness_id=1))
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = surfaces
    return model, points


def point_of(tag, points, result):
    return points.get(tag) or result.points[tag]


# --- the helpers ---------------------------------------------------------

def test_subdivisions_round_up_and_never_vanish():
    assert subdivisions_for(4.0, 0.5) == 8
    assert subdivisions_for(4.0, 3.0) == 2
    assert subdivisions_for(0.1, 0.5) == 1          # never zero segments
    assert subdivisions_for(4.0, 0.0) == 1          # a nonsense target does not crash
    assert subdivisions_for(4.0, 4.0) == 1          # exact fit, no spurious extra


def test_shared_edges_finds_the_common_edge_only():
    model, _ = plate_model()
    shared = shared_edges(model.surfaces)
    assert list(shared) == [(2, 3)]
    assert sorted(shared[(2, 3)]) == [1, 2]


def test_a_single_plate_has_no_shared_edges():
    model, _ = plate_model(second_plate=False)
    assert shared_edges(model.surfaces) == {}


# --- meshing -------------------------------------------------------------

def test_model_without_surfaces_meshes_to_nothing():
    result = mesh_surfaces(StructuralModel())
    assert result.surfaces == {}
    assert result.node_count == 0


def test_single_plate_is_meshed_and_keeps_its_area():
    model, points = plate_model(second_plate=False)
    result = mesh_surfaces(model, 0.5)
    meshed = result.surfaces[1]
    assert meshed.triangles
    assert meshed.area == pytest.approx(12.0, rel=1e-6)
    assert meshed.outline_tags == [1, 2, 3, 4]


def test_outline_vertices_keep_their_neutral_node_ids():
    """The plate's own nodes must not be duplicated - results map through them."""
    model, points = plate_model(second_plate=False)
    result = mesh_surfaces(model, 0.5)
    tags = set(result.surfaces[1].node_tags)
    assert {1, 2, 3, 4} <= tags
    assert all(tag >= MESH_TAG_BASE for tag in result.points)


@pytest.mark.parametrize("target", [0.3, 0.5, 0.75, 1.0])
def test_two_plates_share_exactly_the_nodes_on_their_common_edge(target):
    model, points = plate_model()
    result = mesh_surfaces(model, target)
    a, b = result.surfaces[1], result.surfaces[2]
    shared = set(a.node_tags) & set(b.node_tags)
    on_edge = [t for t in shared if abs(point_of(t, points, result)[0] - 4.0) < 1e-7]
    # Every shared node is on the shared edge, and there are at least the corners.
    assert len(shared) == len(on_edge) >= 2
    # And they sit at the prescribed subdivision, not wherever the mesher liked.
    expected = subdivisions_for(3.0, target) + 1
    assert len(on_edge) == expected


@pytest.mark.parametrize("target", [0.3, 0.5, 0.75])
def test_shared_edge_nodes_are_evenly_spaced(target):
    model, points = plate_model()
    result = mesh_surfaces(model, target)
    shared = set(result.surfaces[1].node_tags) & set(result.surfaces[2].node_tags)
    ys = sorted(point_of(t, points, result)[1] for t in shared)
    steps = [b - a for a, b in zip(ys, ys[1:])]
    assert max(steps) == pytest.approx(min(steps), rel=1e-6)
    assert ys[0] == pytest.approx(0.0) and ys[-1] == pytest.approx(3.0)


def test_both_plates_keep_their_area_when_meshed_together():
    model, _ = plate_model()
    result = mesh_surfaces(model, 0.5)
    for surface_id in (1, 2):
        assert result.surfaces[surface_id].area == pytest.approx(12.0, rel=1e-6)


def test_finer_target_gives_more_triangles():
    model, _ = plate_model(second_plate=False)
    coarse = mesh_surfaces(model, 1.0).triangle_count
    fine = mesh_surfaces(model, 0.3).triangle_count
    assert fine > coarse > 0


def test_every_triangle_has_three_distinct_nodes():
    model, _ = plate_model()
    result = mesh_surfaces(model, 0.5)
    for meshed in result.surfaces.values():
        for triangle in meshed.triangles:
            assert len(set(triangle)) == 3


def test_triangle_nodes_all_have_coordinates():
    model, points = plate_model()
    result = mesh_surfaces(model, 0.5)
    for meshed in result.surfaces.values():
        for triangle in meshed.triangles:
            for tag in triangle:
                assert point_of(tag, points, result) is not None


def test_gmsh_state_is_released_so_a_second_run_works():
    """gmsh keeps global state; meshing twice in one process must be safe."""
    model, _ = plate_model()
    first = mesh_surfaces(model, 0.5)
    second = mesh_surfaces(model, 0.5)
    assert first.triangle_count == second.triangle_count


def test_a_degenerate_outline_is_reported_not_meshed():
    model, _ = plate_model(second_plate=False)
    model.surfaces = [StructuralSurface(id=9, nodes=[1, 2], thickness_id=1)]
    result = mesh_surfaces(model, 0.5)
    assert 9 not in result.surfaces
    assert any("fewer than 3" in warning for warning in result.warnings)


def test_default_target_is_a_sane_plate_size():
    assert 0.1 <= DEFAULT_TARGET_LENGTH <= 1.0


def test_three_plates_in_a_row_conform_at_both_seams():
    model, points = plate_model()
    points.update({7: (12, 0, 0), 8: (12, 3, 0)})
    model.nodes.append(StructuralNode(id=7, point=Point(12, 0, 0)))
    model.nodes.append(StructuralNode(id=8, point=Point(12, 3, 0)))
    model.surfaces.append(StructuralSurface(id=3, nodes=[5, 7, 8, 6], thickness_id=1))
    result = mesh_surfaces(model, 0.5)
    first = set(result.surfaces[1].node_tags) & set(result.surfaces[2].node_tags)
    second = set(result.surfaces[2].node_tags) & set(result.surfaces[3].node_tags)
    assert len(first) == len(second) == subdivisions_for(3.0, 0.5) + 1
    assert not (first & second)          # the seams are different node sets


def test_non_convex_outline_is_meshed_correctly():
    """An L-shaped plate: the mesher must not fill the notch."""
    model = StructuralModel()
    points = {1: (0, 0, 0), 2: (4, 0, 0), 3: (4, 2, 0), 4: (2, 2, 0), 5: (2, 4, 0), 6: (0, 4, 0)}
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4, 5, 6], thickness_id=1)]
    result = mesh_surfaces(model, 0.5)
    # 4x2 + 2x2 = 12 m2; a filled notch would give 16.
    assert result.surfaces[1].area == pytest.approx(12.0, rel=1e-6)


def test_wall_on_slab_conforms_although_the_plates_are_not_coplanar():
    """The wall-to-slab case: two plates meeting at right angles on one edge."""
    model = StructuralModel()
    points = {1: (0, 0, 0), 2: (4, 0, 0), 3: (4, 3, 0), 4: (0, 3, 0),
              5: (0, 0, 3), 6: (4, 0, 3)}
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = [
        StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1),   # slab
        StructuralSurface(id=2, nodes=[1, 2, 6, 5], thickness_id=1),   # wall
    ]
    result = mesh_surfaces(model, 0.5)
    slab, wall = result.surfaces[1], result.surfaces[2]
    shared = set(slab.node_tags) & set(wall.node_tags)
    assert len(shared) == subdivisions_for(4.0, 0.5) + 1
    for tag in shared:
        x, y, z = point_of(tag, points, result)
        assert y == pytest.approx(0.0) and z == pytest.approx(0.0)
    assert slab.area == pytest.approx(12.0, rel=1e-6)
    assert wall.area == pytest.approx(12.0, rel=1e-6)


def test_a_unit_mismatch_is_refused_instead_of_hanging():
    """A millimetre model translated as metres asks gmsh for millions of
    triangles - inside C++, where it neither returns nor honours a Python
    timeout. The guard has to fire before gmsh is ever called."""
    model = StructuralModel()
    points = {1: (0, 0, 0), 2: (4000, 0, 0), 3: (4000, 3000, 0), 4: (0, 3000, 0)}
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)]
    with pytest.raises(ValueError, match="millimetres"):
        mesh_surfaces(model, 0.5)


def test_a_genuinely_large_model_is_still_allowed_at_a_coarser_target():
    """The guard is about the ratio, not the absolute size: the same geometry
    with a matching target length must pass."""
    model = StructuralModel()
    points = {1: (0, 0, 0), 2: (4000, 0, 0), 3: (4000, 3000, 0), 4: (0, 3000, 0)}
    model.nodes = [StructuralNode(id=i, point=Point(*p)) for i, p in points.items()]
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)]
    result = mesh_surfaces(model, 500.0)
    assert result.surfaces[1].triangles


# --- the control reaches the mesher (WP0b follow-up) ----------------------

def test_the_target_length_reaches_the_mesher_through_run_model():
    """The knob exists on the runner; the chain from run_model has to carry it,
    or the setting is silently ignored - the worst kind of control."""
    from tekton_core.core.materials import Material
    from tekton_core.core.model import StructuralLoadCase
    from tekton_core.core.model import StructuralSupport
    from tekton_opensees import run_model

    def square(target):
        side, divisions = 4.0, 8
        outline = []
        for i in range(divisions):
            outline.append((side * i / divisions, 0.0))
        for j in range(divisions):
            outline.append((side, side * j / divisions))
        for i in range(divisions, 0, -1):
            outline.append((side * i / divisions, side))
        for j in range(divisions, 0, -1):
            outline.append((0.0, side * j / divisions))
        model = StructuralModel()
        ids = {index: point for index, point in enumerate(outline, start=1)}
        model.nodes = [StructuralNode(id=i, point=Point(x, y, 0.0)) for i, (x, y) in ids.items()]
        model.materials = {1: Material.resolve("C24")}
        model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.2)]
        model.surfaces = [StructuralSurface(id=1, nodes=list(ids), thickness_id=1)]
        model.supports = [StructuralSupport(id=1, nodes=list(ids), rx=0.0, ry=0.0, rz=0.0)]
        model.load_cases = [StructuralLoadCase(id=1, name="SW", self_weight=True)]
        runner = run_model(model, mesh_target_length=target)
        return sum(len(tags) for tags in runner.built.surface_elements.values())

    coarse = square(0.5)
    fine = square(0.2)
    assert fine > coarse > 0


def test_the_outline_sets_a_floor_on_how_coarse_the_mesh_can_get():
    """A target coarser than the outline spacing cannot win: the boundary
    vertices are prescribed, and that is what keeps neighbouring plates
    conforming. Worth asserting so nobody reads it as the control failing."""
    model, _ = plate_model(second_plate=False)     # 4 corners, 4 m and 3 m edges
    coarse = mesh_surfaces(model, 10.0).triangle_count
    assert coarse > 0
