"""Plate translation and export.

compas_timber's plate surfaces do not share nodes, so without explicit
connections the plates are separate pieces and the model is a mechanism.
"""

import pytest
from compas.data import json_load
from compas.geometry import Vector

from compas_timber_fea.core.joint_policy import PlateConnectionPolicy
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralSurfaceConnection
from compas_timber_fea.core.releases import MemberRelease
from compas_timber_fea.translator import TimberToStructural

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")

from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper  # noqa: E402

PLATES = "tests/timber_model_plates_2.json"


@pytest.fixture
def plate_model():
    """The fixture is authored in millimetres."""
    return TimberToStructural(source_units="mm").translate(json_load(PLATES))


def test_plates_become_surfaces(plate_model):
    assert len(plate_model.surfaces) == 4
    assert plate_model.thicknesses


def test_thickness_is_converted_to_meters(plate_model):
    """A 200 mm panel must not arrive as a 200 m one."""
    assert all(0.01 < t.thickness < 1.0 for t in plate_model.thicknesses)


def test_surfaces_map_back_to_their_source_plate(plate_model):
    """The analytical surface is regenerated each run, so its own guid is useless."""
    source_plates = json_load(PLATES)
    plate_guids = {str(plate.guid) for plate in source_plates.plates}

    for surface in plate_model.surfaces:
        assert surface.source_element_id in plate_guids


def test_surfaces_carry_a_span_direction(plate_model):
    """Timber panels are orthotropic; an orientation is required to express that."""
    for surface in plate_model.surfaces:
        assert isinstance(surface.span_direction, Vector)
        assert surface.span_direction.length == pytest.approx(1.0, abs=1e-6)


def test_plate_connections_name_both_plates(plate_model):
    assert plate_model.surface_connections
    for connection in plate_model.surface_connections:
        assert len(connection.source_element_ids) == 2


def test_plate_connections_default_to_hinged_edges(plate_model):
    """Panel joints transfer little bending; assuming continuity overstates stiffness.

    Along an edge only rotation about the edge axis is meaningful, so that is
    the degree of freedom released.
    """
    for connection in plate_model.surface_connections:
        assert connection.release is not None
        assert connection.release.released_dofs() == ("rx",)


def test_continuous_policy_makes_connections_rigid():
    model = TimberToStructural(source_units="mm", plate_policy=PlateConnectionPolicy.continuous()).translate(json_load(PLATES))

    for connection in model.surface_connections:
        assert connection.release.is_rigid()


def test_plate_translation_is_reported(plate_model):
    translator = TimberToStructural(source_units="mm")
    translator.translate(json_load(PLATES))

    assert any("plate edge" in entry for entry in translator.report)


def test_plate_model_survives_serialization(plate_model, tmp_path):
    path = tmp_path / "plates.json"
    plate_model.to_json(path)

    loaded = StructuralModel.from_json(path)

    assert len(loaded.surfaces) == len(plate_model.surfaces)
    assert isinstance(loaded.surfaces[0].span_direction, Vector)
    connection = loaded.surface_connections[0]
    assert isinstance(connection.release, MemberRelease)
    assert connection.source_element_ids


# -- export -----------------------------------------------------------------


@pytest.fixture
def surface_mapper():
    return SurfaceMapper(rfem.structure_core, types_for_lines=rfem.types_for_lines)


def _two_plates():
    model = StructuralModel()
    model.surfaces.append(StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1))
    model.surfaces.append(StructuralSurface(id=2, nodes=[5, 6, 7, 8], thickness_id=1))
    model.surface_connections.append(
        StructuralSurfaceConnection(id=1, nodes=[1, 2], release=MemberRelease.pinned())
    )
    return model


def test_hinged_connection_becomes_a_line_hinge(surface_mapper):
    model = _two_plates()
    model.surface_connections[0].release = MemberRelease.hinged_edge()
    for surface in model.surfaces:
        surface_mapper.map(surface)

    hinges = surface_mapper.map_connections(model.surface_connections)

    assert len(hinges) == 1
    assert hinges[0].assigned_to, "hinge is not attached to any line"
    # The released rotation must actually reach RFEM, not just the neutral model.
    assert hinges[0].rotational_release_phi_x == 0.0
    assert hinges[0].translational_release_u_z == float("inf")


def test_continuous_connection_needs_no_hinge(surface_mapper):
    model = _two_plates()
    model.surface_connections[0].release = MemberRelease.rigid()
    for surface in model.surfaces:
        surface_mapper.map(surface)

    assert surface_mapper.map_connections(model.surface_connections) == []


def test_connections_sharing_a_release_share_one_hinge(surface_mapper):
    model = _two_plates()
    model.surface_connections.append(
        StructuralSurfaceConnection(id=2, nodes=[5, 6], release=MemberRelease.pinned())
    )
    for surface in model.surfaces:
        surface_mapper.map(surface)

    hinges = surface_mapper.map_connections(model.surface_connections)

    assert len(hinges) == 1
    # Both edges are listed on the single hinge.
    assert len(hinges[0].assigned_to.split(",")) == 2


def test_translating_twice_does_not_double_the_surfaces():
    """The model appends structural surfaces on generation; a Grasshopper re-solve must not stack them."""
    timber_model = json_load(PLATES)
    first = TimberToStructural(source_units="mm").translate(timber_model)
    second = TimberToStructural(source_units="mm").translate(timber_model)

    assert len(second.surfaces) == len(first.surfaces)
    assert len(second.surface_connections) == len(first.surface_connections)
