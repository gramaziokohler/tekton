"""What an engineer's RFEM model has that a translated one lacked (2026-11-17).

Read off "Tragwerkskonzept 1 - Ingrid": V-columns hinged at both ends, supports
of RFEM's 'hinged' preset (rotation about z held), a roof pressure on a load
transfer surface, girders designed as member sets - and a run must never write
into the engineer's open model.
"""

import pytest
from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Vector
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.core.load_distribution import apply_area_load
from compas_timber_fea.core.load_distribution import distribute_area_load
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.serialization import model_from_json
from compas_timber_fea.core.serialization import model_to_json
from compas_timber_fea.core.support_types import SUPPORT_TYPES
from compas_timber_fea.translator import TimberToStructural


def _beam(start, end, **attributes):
    beam = Beam.from_centerline(Line(start, end), width=0.2, height=0.4)
    beam.attributes.update(attributes)
    return beam


def _portal(column_releases=None, girder_set=None):
    """Two columns and a girder in two pieces over a middle column top: a small V-column bay."""
    model = TimberModel()
    for x in (0.0, 4.0, 8.0):
        column = _beam((x, 0, 0), (x, 0, 3), category="vcolumn", support_points=[(x, 0.0, 0.0)])
        if column_releases:
            column.attributes["end_releases"] = column_releases
        model.add_element(column)
    for a, b in (((0, 0, 3), (4, 0, 3)), ((4, 0, 3), (8, 0, 3))):
        girder = _beam(a, b, category="girder")
        if girder_set:
            girder.attributes["member_set"] = girder_set
        model.add_element(girder)
    return model


def _members_of(structural, category_points):
    nodes = {n.id: n.point for n in structural.nodes}
    out = []
    for m in structural.members:
        a, b = nodes[m.node_start], nodes[m.node_end]
        if abs(a.x - b.x) < 1e-9 and abs(a.y - b.y) < 1e-9:
            out.append(m)
    return out


# --- supports ----------------------------------------------------------------------


def test_rfem_hinged_support_holds_the_twist_only():
    s = SUPPORT_TYPES["pinned_rz"]
    assert (s["ux"], s["uy"], s["uz"]) == (float("inf"),) * 3
    assert (s["rx"], s["ry"]) == (0.0, 0.0)
    assert s["rz"] == float("inf")


# --- member end releases --------------------------------------------------------------


def test_a_column_hinged_at_both_ends_gets_member_hinges():
    structural = TimberToStructural().translate(_portal(column_releases="pinned"))
    columns = _members_of(structural, None)
    assert len(columns) == 3
    for c in columns:
        released = [r for r in (c.release_start, c.release_end) if r is not None]
        # the foot: every member end there is a hinge, so one is kept continuous
        assert released, "column without any hinge"
        for r in released:
            assert r.released_dofs() == ("ry", "rz")  # bending free, torsion kept


def test_girders_stay_continuous_when_only_columns_are_hinged():
    structural = TimberToStructural().translate(_portal(column_releases="pinned"))
    columns = {m.id for m in _members_of(structural, None)}
    for m in structural.members:
        if m.id not in columns and m.source_element_type == "beam":
            assert m.release_start is None and m.release_end is None


def test_a_node_where_every_end_is_hinged_keeps_one_continuous():
    """A lone column foot hinged on a pinned support is singular; n-1 hinges are the same mechanics."""
    translator = TimberToStructural()
    structural = translator.translate(_portal(column_releases="pinned"))
    nodes = {n.id: n.point for n in structural.nodes}
    for m in _members_of(structural, None):
        foot = m.node_start if nodes[m.node_start].z < nodes[m.node_end].z else m.node_end
        release = m.release_start if foot == m.node_start else m.release_end
        assert release is None  # the only member at its foot: kept continuous
    assert any("every member end was hinged" in line for line in translator.report)


def test_unknown_release_name_is_refused():
    with pytest.raises(ValueError, match="end release"):
        TimberToStructural().translate(_portal(column_releases="wobbly"))


# --- member sets ----------------------------------------------------------------------


def test_girder_pieces_sharing_a_key_become_one_continuous_member_set():
    structural = TimberToStructural().translate(_portal(girder_set="girder-1"))
    assert len(structural.member_sets) == 1
    member_set = structural.member_sets[0]
    assert member_set.set_type == "continuous"
    assert member_set.name == "girder-1"
    assert len(member_set.member_ids) == 2


def test_single_members_get_no_member_set():
    structural = TimberToStructural().translate(_portal())
    assert structural.member_sets == []


def test_member_sets_survive_serialisation(tmp_path):
    structural = TimberToStructural().translate(_portal(girder_set="g"))
    path = str(tmp_path / "model.json")
    model_to_json(structural, path)
    back = model_from_json(path)
    assert [s.member_ids for s in back.member_sets] == [s.member_ids for s in structural.member_sets]


# --- area loads on a shaped roof ------------------------------------------------------


def _grid(heights):
    """A 2x1 field beam grid (x 0..8, y 0..4), node z from `heights[(x, y)]`."""
    model = StructuralModel()
    ids = {}
    for (x, y), z in heights.items():
        ids[(x, y)] = len(ids) + 1
        model.nodes.append(StructuralNode(id=ids[(x, y)], point=Point(x, y, z)))
    pairs = [((0, 0), (4, 0)), ((4, 0), (8, 0)), ((0, 4), (4, 4)), ((4, 4), (8, 4)),
             ((0, 0), (0, 4)), ((4, 0), (4, 4)), ((8, 0), (8, 4))]
    for k, (a, b) in enumerate(pairs, start=1):
        model.members.append(StructuralMember(id=k, node_start=ids[a], node_end=ids[b], section_id=1))
    return model


FLAT = {(0, 0): 3.0, (4, 0): 3.0, (8, 0): 3.0, (0, 4): 3.0, (4, 4): 3.0, (8, 4): 3.0}
FOLDED = {**FLAT, (4, 0): 3.3, (4, 4): 3.3}  # a ridge along x = 4


def test_a_folded_roof_has_no_single_level_without_a_band():
    _, info = distribute_area_load(_grid(FOLDED), (0, 0, -1))
    assert info["panels_loaded"] == 0


def test_a_band_loads_the_whole_folded_roof():
    loads, info = distribute_area_load(_grid(FOLDED), (0, 0, -1), band=0.5, slope=0.25)
    assert info["panels_loaded"] == 2
    assert info["area"] == pytest.approx(32.0)  # in plan
    assert sum(f[2] * 1 for f in loads.values()) < 0
    assert len(info["fields"]) == 2 and all(len(f["nodes"]) == 4 for f in info["fields"])


def test_the_band_leaves_a_flat_roof_unchanged():
    a, _ = distribute_area_load(_grid(FLAT), (0, 0, -2))
    b, _ = distribute_area_load(_grid(FLAT), (0, 0, -2), band=0.5, slope=0.25)
    assert a == pytest.approx(b)


def test_apply_area_load_keeps_the_area_next_to_its_member_loads():
    model = _grid(FOLDED)
    report = []
    apply_area_load(model, {"pressure": [0, 0, -2.5], "load_case_id": 1, "band": 0.5,
                            "transfer_surface": True, "name": "Auflast"}, report=report)
    assert len(model.area_loads) == 1
    area = model.area_loads[0]
    assert area.transfer_surface
    assert sorted(area.member_load_ids) == sorted(load.id for load in model.member_loads)
    total = sum(load.force.z * _length(model, load.member_id) for load in model.member_loads)
    assert total == pytest.approx(-2.5 * 32.0)
    assert "band" in report[0]


def _length(model, member_id):
    nodes = {n.id: n.point for n in model.nodes}
    m = next(m for m in model.members if m.id == member_id)
    a, b = nodes[m.node_start], nodes[m.node_end]
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5  # the 45-degree widths are per plan metre


# --- RFEM: member sets, load transfer surfaces, the target model ------------------------


def test_member_set_maps_to_a_continuous_rfem_member_set():
    from dlubal.api import rfem

    from compas_dlubal.dlubal.mappers.mapper_sets import MemberSetMapper
    from compas_dlubal.dlubal.numbering import Numbering

    structural = TimberToStructural().translate(_portal(girder_set="g"))
    obj = MemberSetMapper(rfem.structure_core, Numbering()).map(structural.member_sets[0])
    kind = rfem.structure_core.MemberSet.DESCRIPTOR.fields_by_name["set_type"].enum_type.values_by_number[obj.set_type].name
    assert kind == "SET_TYPE_CONTINUOUS"
    assert list(obj.members) == structural.member_sets[0].member_ids


class _FakeMember:
    def __init__(self, no, line):
        self.no, self.line = no, line


class _FakeApplication:
    """RFEM after the push: every member has a line (here 100 + its number)."""

    def __init__(self, members, numbering):
        self.numbers = [numbering.member(m.id) for m in members]

    def get_object_list(self, objs):
        return [_FakeMember(no, 100 + no) for no in self.numbers]


def _transfer_objects(heights):
    from dlubal.api import rfem

    from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper
    from compas_dlubal.dlubal.mappers.mapper_sets import LoadTransferMapper
    from compas_dlubal.dlubal.backend_map_io import load_map
    from compas_dlubal.dlubal.numbering import Numbering
    from compas_dlubal.dlubal.numbering import number_model

    model = _grid(heights)
    apply_area_load(model, {"pressure": [0, 0, -2.5], "load_case_id": 1, "band": 0.5, "transfer_surface": True})
    backend_map = load_map(None, "rfem")
    number_model(model, backend_map)  # as the importer does: every push has a map
    numbering = Numbering(backend_map)
    loads = LoadMapper(rfem.loading, Loads=rfem.loads, numbering=numbering)
    mapper = LoadTransferMapper(rfem, numbering, loads)
    objects = mapper.build(_FakeApplication(model.members, numbering), model)
    return model, mapper, objects, numbering


def test_planar_fields_become_load_transfer_surfaces_with_their_members_lines():
    from dlubal.api import rfem

    model, mapper, objects, numbering = _transfer_objects(FLAT)
    surfaces = [o for o in objects if isinstance(o, rfem.structure_core.Surface)]
    loads = [o for o in objects if isinstance(o, rfem.loads.SurfaceLoad)]
    assert mapper.report == {"surfaces": 2, "triangulated_fields": 0, "fields_as_member_loads": 0}
    assert all(set(s.boundary_lines) <= {100 + numbering.member(m.id) for m in model.members} for s in surfaces)
    assert len(loads) == 1 and sorted(loads[0].surfaces) == sorted(s.no for s in surfaces)
    assert loads[0].uniform_magnitude == pytest.approx(2500.0)  # N/m2, RFEM's Z points down
    assert mapper.skipped_member_loads(model) == {load.id for load in model.member_loads}


def test_a_warped_field_becomes_two_triangles_with_a_free_diagonal():
    from dlubal.api import rfem

    warped = {**FLAT, (8, 4): 3.2}  # the second field's corner lifted: not planar
    model, mapper, objects, numbering = _transfer_objects(warped)
    assert mapper.report == {"surfaces": 3, "triangulated_fields": 1, "fields_as_member_loads": 0}
    lines = [o for o in objects if isinstance(o, rfem.structure_core.Line)]
    surfaces = [o for o in objects if isinstance(o, rfem.structure_core.Surface)]
    member_lines = {100 + numbering.member(m.id) for m in model.members}
    assert len(lines) == 1 and lines[0].no not in member_lines
    triangles = [s for s in surfaces if lines[0].no in s.boundary_lines]
    assert len(triangles) == 2
    for t in triangles:
        assert len(t.boundary_lines) == 3 and len(t.loaded_members) == 2
    loads = [o for o in objects if isinstance(o, rfem.loads.SurfaceLoad)]
    assert len(loads) == 1 and sorted(loads[0].surfaces) == sorted(s.no for s in surfaces)


def test_fan_apex_skips_a_corner_in_the_middle_of_a_side():
    from compas_dlubal.dlubal.mappers.mapper_sets import _fan_apex

    # from corner 0 the last triangle (4,0) (0,0) (2,0) is a sliver along the bottom side
    assert _fan_apex([[4, 0], [4, 3], [0, 3], [0, 0], [2, 0]]) not in (0, None)
    assert _fan_apex([[0, 0], [1, 0], [2, 0]]) is None


class _FakeModels:
    def __init__(self, names, active):
        from dlubal.api.common.model_id_pb2 import ModelId

        self.infos = [type("info", (), {"name": n, "guid": "g-" + n})() for n in names]
        self.active = ModelId(guid="g-" + active)
        self.created = []

    def get_model_list(self):
        return type("list", (), {"model_info": self.infos})()

    def get_active_model(self):
        return self.active

    def set_active_model(self, model_id):
        self.active = model_id

    def create_model(self, name):
        from dlubal.api.common.model_id_pb2 import ModelId

        self.created.append(name)
        self.infos.append(type("info", (), {"name": name, "guid": "g-" + name})())
        return ModelId(guid="g-" + name)


def _client(app):
    from compas_dlubal.dlubal.client import DlubalClient

    client = DlubalClient(api_key="k")
    client.application = app
    return client


def test_a_run_never_writes_into_the_engineers_open_model():
    app = _FakeModels(["Tragwerkskonzept 1 - Ingrid"], active="Tragwerkskonzept 1 - Ingrid")
    name, created = _client(app).use_model("tekton-gh")
    assert created and app.created == ["tekton-gh"]
    assert app.active.guid == "g-tekton-gh"


def test_an_open_model_of_our_name_is_reused():
    app = _FakeModels(["Ingrid", "tekton-gh"], active="Ingrid")
    _, created = _client(app).use_model("tekton-gh")
    assert not created and app.created == []
    assert app.active.guid == "g-tekton-gh"


def test_no_name_no_push():
    with pytest.raises(ValueError):
        _client(_FakeModels(["x"], active="x")).use_model("")


def test_the_reader_selects_its_model_and_never_creates_one():
    """RFEM's active model is per connection: the reader must pick ours, not the GUI's."""
    app = _FakeModels(["Ingrid", "tekton-gh"], active="Ingrid")
    client = _client(app)
    client.select_model("tekton-gh")
    assert app.active.guid == "g-tekton-gh"
    with pytest.raises(RuntimeError, match="push it first"):
        client.select_model("missing")
    assert app.created == []


def test_a_rectangle_goes_to_rfem_by_its_parameters_not_its_name():
    """RFEM reads dimensions in a name in model units (mm): 'R_M1 0.28/1' was 0.28 x 1 mm."""
    from dlubal.api import rfem

    from compas_dlubal.dlubal.mappers.mapper_members import MemberMapper
    from compas_timber_fea.core.model import StructuralSection

    cs = MemberMapper(rfem.structure_core).map_section(
        StructuralSection(id=1, name="R_M1 0.28/1", material_id=1, width=0.28, height=1.0))
    assert (cs.b, cs.h) == (0.28, 1.0)
    assert cs.name == ""  # RFEM names it from the parameters
