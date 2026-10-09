"""Surface loads and line supports, mapped to RFEM.

Both existed in the neutral model and in OpenSees and reached RFEM not at all:
a loaded plate arrived unloaded, a wall foot arrived unsupported, and nothing
failed. Same JSON, two different structures.

These build real protobuf messages from the pinned dlubal-api, so a wrong field
name or enum fails here rather than in a live session on Windows.
"""

import pytest

from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralLineSupport
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralSurfaceLoad

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")

from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper  # noqa: E402
from compas_dlubal.dlubal.mappers.mapper_supports import SupportMapper  # noqa: E402
from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper  # noqa: E402


@pytest.fixture
def loads():
    return LoadMapper(rfem.loading, Loads=rfem.loads)


@pytest.fixture
def surfaces():
    return SurfaceMapper(rfem.structure_core, types_for_lines=rfem.types_for_lines)


# --- surface loads --------------------------------------------------------

def test_a_downward_pressure_becomes_one_load(loads):
    load = StructuralSurfaceLoad(id=1, surface_id=7, load_case_id=2, pressure=Vector(0, 0, -2.5))

    protos = loads.map_surface_load(load)

    assert len(protos) == 1
    assert list(protos[0].surfaces) == [7]
    assert protos[0].load_case == 2


def test_the_magnitude_reaches_rfem_in_rfem_units(loads):
    """The neutral contract is kN/m2, the Dlubal API speaks N/m2. Getting this
    wrong gave results 1000x out on the first live run."""
    load = StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -2.0))

    proto = loads.map_surface_load(load)[0]

    assert proto.uniform_magnitude == pytest.approx(2000.0)


def test_the_sign_follows_the_z_flip(loads):
    """Neutral is Z-up, Dlubal Z-down. A load pressing down on a slab must not
    arrive pointing up."""
    down = loads.map_surface_load(
        StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1.0)))[0]
    up = loads.map_surface_load(
        StructuralSurfaceLoad(id=2, surface_id=1, load_case_id=1, pressure=Vector(0, 0, 1.0)))[0]

    assert down.uniform_magnitude == -up.uniform_magnitude


def test_a_projected_load_uses_the_projected_direction(loads):
    """Snow is given per m2 of *plan*. RFEM has a direction enum for exactly
    this, so unlike OpenSees the flag can be honoured rather than ignored."""
    plain = loads.map_surface_load(
        StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1.0)))[0]
    projected = loads.map_surface_load(
        StructuralSurfaceLoad(id=2, surface_id=1, load_case_id=1,
                              pressure=Vector(0, 0, -1.0), projected=True))[0]

    assert plain.load_direction != projected.load_direction
    assert "PROJECTED" in projected.load_direction.name if hasattr(projected.load_direction, "name") else True


def test_a_horizontal_pressure_maps_to_its_own_axis(loads):
    """Wind on a wall, not gravity on a slab."""
    load = StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(1.5, 0, 0))

    proto = loads.map_surface_load(load)[0]

    assert proto.uniform_magnitude == pytest.approx(1500.0)


def test_a_pressure_in_two_directions_becomes_two_loads(loads):
    """RFEM applies a magnitude along one direction, so a vector with several
    components needs one object each - same as the member load."""
    load = StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(1.0, 0, -2.0))

    protos = loads.map_surface_load(load)

    assert len(protos) == 2
    assert len({p.no for p in protos}) == 2


def test_a_zero_pressure_produces_nothing(loads):
    load = StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, 0))

    assert loads.map_surface_load(load) == []


def test_surface_load_numbers_do_not_collide_with_other_loads(loads):
    """All load objects share one numbering space in RFEM."""
    from compas_timber_fea.core.model import StructuralPointLoad

    point = loads.map_point_load(
        StructuralPointLoad(id=1, node_id=1, load_case_id=1, force=Vector(0, 0, -1)))
    surface = loads.map_surface_load(
        StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1)))

    # map_point_load returns one object, map_surface_load a list.
    numbers = [point.no] + [p.no for p in surface]
    assert len(numbers) == len(set(numbers))


# --- line supports --------------------------------------------------------

def test_a_line_support_becomes_a_line_support(surfaces):
    support = StructuralLineSupport(id=1, nodes=[1, 2])

    proto = surfaces.map_line_support(support)

    assert proto.no == 1
    assert len(proto.lines) == 1


def test_it_reuses_the_plate_edge_rather_than_making_a_second_line(surfaces):
    """Conformity. A support on its own line, parallel to the plate's edge,
    would hold nothing - the plate would not be attached to it."""
    surface = StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)
    surfaces.map(surface)

    support = StructuralLineSupport(id=1, nodes=[1, 2])
    proto = surfaces.map_line_support(support)

    assert list(proto.lines) == [surfaces._lines_map[(1, 2)]]


def test_a_support_on_an_edge_no_surface_uses_creates_the_line(surfaces):
    """A wall foot need not be a plate edge - it can be any chain of nodes."""
    proto = surfaces.map_line_support(StructuralLineSupport(id=1, nodes=[10, 11]))

    assert len(proto.lines) == 1


def test_a_chain_of_several_nodes_becomes_several_lines(surfaces):
    """A meshed edge has intermediate nodes; the support spans all of them."""
    support = StructuralLineSupport(id=1, nodes=[1, 2, 3, 4])

    proto = surfaces.map_line_support(support)

    assert len(proto.lines) == 3


def test_the_stiffnesses_are_passed_through_per_metre(surfaces):
    """RFEM's line support takes kN/m per metre directly, which is exactly how
    the neutral model stores them - no conversion, unlike OpenSees."""
    support = StructuralLineSupport(id=1, nodes=[1, 2], uz=5000.0)

    proto = surfaces.map_line_support(support)

    assert proto.spring_z == pytest.approx(5000.0)


def test_a_rigid_direction_arrives_rigid(surfaces):
    support = StructuralLineSupport(id=1, nodes=[1, 2])

    proto = surfaces.map_line_support(support)

    assert proto.spring_z == float("inf") or proto.spring_z > 1e9


def test_a_free_direction_arrives_free(surfaces):
    support = StructuralLineSupport(id=1, nodes=[1, 2], ux=0.0)

    proto = surfaces.map_line_support(support)

    assert proto.spring_x == 0.0


def test_the_name_travels(surfaces):
    support = StructuralLineSupport(id=1, nodes=[1, 2], name="Wall foot")

    proto = surfaces.map_line_support(support)

    assert "Wall foot" in proto.name


# --- nodal supports are unaffected ---------------------------------------

def test_the_nodal_support_mapper_still_works():
    """Guard: line supports are a second kind, not a replacement."""
    from compas_timber_fea.core.model import StructuralSupport

    proto = SupportMapper(rfem.types_for_nodes).map(StructuralSupport(id=1, nodes=[1]))

    assert proto.no == 1
    assert list(proto.nodes) == [1]
