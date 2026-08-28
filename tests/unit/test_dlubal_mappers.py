"""Offline tests for the Dlubal mappers.

These construct real protobuf messages from the pinned dlubal-api package, so
they catch field-name and field-type mistakes without a running RFEM instance.
"""

import math

import pytest

from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralThickness
from compas_timber_fea.core.releases import MemberRelease

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")

from compas_dlubal.dlubal.mappers.mapper_members import MemberMapper  # noqa: E402
from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper  # noqa: E402
from compas_dlubal.dlubal.mappers.mapper_thicknesses import ThicknessMapper  # noqa: E402


@pytest.fixture
def core():
    return rfem.structure_core


def test_thickness_maps_to_valid_proto(core):
    thickness = StructuralThickness(id=1, name="Thickness 0.200m", material_id=2, thickness=0.2)

    proto = ThicknessMapper(core).map(thickness)

    assert proto.no == 1
    assert proto.material == 2
    assert proto.uniform_thickness == pytest.approx(0.2)


def test_surface_boundary_lines_are_node_numbers(core):
    surface = StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1)

    objects = SurfaceMapper(core).map(surface)

    lines, dlubal_surface = objects[:-1], objects[-1]
    # A quad has four boundary lines, each defined by two node numbers.
    assert len(lines) == 4
    assert [list(line.definition_nodes) for line in lines] == [[1, 2], [2, 3], [3, 4], [4, 1]]
    assert list(dlubal_surface.boundary_lines) == [line.no for line in lines]
    assert dlubal_surface.thickness == 1


def test_shared_edges_reuse_the_same_line(core):
    """Adjacent surfaces must reference one shared line, or the mesh is discontinuous."""
    mapper = SurfaceMapper(core)

    first = mapper.map(StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1))
    second = mapper.map(StructuralSurface(id=2, nodes=[3, 2, 5, 6], thickness_id=1))

    # Edge (2, 3) is common to both surfaces despite opposite direction, so the
    # second surface emits only three new lines and reuses the existing one.
    assert len(second) - 1 == 3
    shared_line = mapper._lines_map[(2, 3)]
    assert shared_line in list(first[-1].boundary_lines)
    assert shared_line in list(second[-1].boundary_lines)


@pytest.fixture
def member_mapper():
    return MemberMapper(rfem.structure_core, nodes_cache={}, types_for_members=rfem.types_for_members)


def _member(member_id, release=None):
    return StructuralMember(id=member_id, node_start=member_id, node_end=member_id + 1, section_id=1, release_start=release)


def test_pinned_release_becomes_a_member_hinge(member_mapper):
    hinges = member_mapper.map_hinges_for_members([_member(1, MemberRelease.pinned())])

    assert len(hinges) == 1
    hinge = hinges[0]
    # Bending released, everything else restrained.
    assert hinge.moment_release_my == 0.0
    assert hinge.moment_release_mz == 0.0
    assert hinge.axial_release_n == math.inf
    assert hinge.moment_release_mt == math.inf


def test_member_references_its_hinge(member_mapper):
    member = _member(1, MemberRelease.pinned())
    member_mapper.map_hinges_for_members([member])

    proto = member_mapper.map_member(member)

    assert proto.member_hinge_start == 1


def test_identical_releases_share_one_hinge(member_mapper):
    members = [_member(1, MemberRelease.pinned()), _member(2, MemberRelease.pinned())]

    hinges = member_mapper.map_hinges_for_members(members)

    assert len(hinges) == 1
    assert member_mapper.map_member(members[0]).member_hinge_start == member_mapper.map_member(members[1]).member_hinge_start


def test_spring_stiffness_reaches_the_hinge(member_mapper):
    """EC5 connection stiffness must survive into RFEM, not collapse to a hinge."""
    springy = MemberRelease(ry=1500.0, rz=1500.0, name="Kser")

    hinges = member_mapper.map_hinges_for_members([_member(1, springy)])

    assert hinges[0].moment_release_my == 1500.0
    assert hinges[0].name == "Kser"


def test_rigid_members_get_no_hinge(member_mapper):
    hinges = member_mapper.map_hinges_for_members([_member(1, MemberRelease.rigid()), _member(2, None)])

    assert hinges == []
    assert member_mapper.map_member(_member(1)).member_hinge_start == 0


def test_hinged_coupling_needs_no_separate_hinge(member_mapper):
    """RFEM's coupling type is already a hinge-hinge link."""
    coupling = StructuralMember(
        id=1, node_start=1, node_end=2, section_id=1,
        member_type="COUPLING", release_start=MemberRelease.pinned(), release_end=MemberRelease.pinned(),
    )

    hinges = member_mapper.map_hinges_for_members([coupling])
    proto = member_mapper.map_member(coupling)

    assert hinges == []
    assert proto.type == 24


def test_springy_coupling_becomes_a_rigid_member_with_hinges(member_mapper):
    """A spring cannot be expressed by the coupling type, so it needs real hinges."""
    springy = MemberRelease(ry=1500.0, rz=1500.0, name="Kser")
    coupling = StructuralMember(
        id=1, node_start=1, node_end=2, section_id=1,
        member_type="COUPLING", release_start=springy, release_end=springy,
    )

    hinges = member_mapper.map_hinges_for_members([coupling])
    proto = member_mapper.map_member(coupling)

    assert len(hinges) == 1
    assert proto.type == 2
    assert proto.member_hinge_start == 1
    assert proto.member_hinge_end == 1
