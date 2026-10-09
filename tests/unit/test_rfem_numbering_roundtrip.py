"""Push with RFEM's numbers, read back with ours.

Until now `no = member.id`, 1:1 in both directions. That worked only because
the neutral ids were small counters. They are hashes now (WP6 step 2), spread
over 2^31, while RFEM documents 999,999 objects per category - so the push
would be outside the documented capacity, and the proto field is a *signed*
int32 that accepts an oversized number without complaint.

The two directions have to change together. A push that writes dense numbers
while the reader still treats the table number as a neutral id would attach
every result to the wrong object, and nothing would fail - the numbers would
simply be wrong, on objects that exist.

These tests pin both ends against one map.
"""

import pytest

from compas.geometry import Point

from compas_timber_fea.core.backend_map import MAX_RFEM_NUMBER
from compas_timber_fea.core.backend_map import BackendMap
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.translator import stable_id

pandas = pytest.importorskip("pandas", reason="result parsing needs pandas")

from compas_dlubal.dlubal.numbering import number_model  # noqa: E402
from compas_dlubal.dlubal.result_parsing import parse_member_internal_forces  # noqa: E402
from compas_dlubal.dlubal.result_parsing import parse_node_deformations  # noqa: E402


def _model():
    model = StructuralModel()
    model.materials[1] = "C24"
    a = stable_id("node", 0.0, 0.0, 0.0)
    b = stable_id("node", 4.0, 0.0, 0.0)
    model.nodes.append(StructuralNode(id=a, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=b, point=Point(4, 0, 0)))
    model.sections.append(StructuralSection(id=1, name="R", material_id=1, width=0.1, height=0.2))
    model.members.append(
        StructuralMember(id=stable_id("member", "guid", "s"), node_start=a, node_end=b, section_id=1))
    model.supports.append(StructuralSupport(id=1, nodes=[a]))
    return model


def _forces_frame(member_no, axial_kn=1.0):
    """One station of one member, as RFEM's table reports it - in N, which is
    what the Dlubal API speaks; the parser converts to the neutral kN."""
    return pandas.DataFrame([{
        "member_no": member_no, "location_x": 0.0,
        "n": axial_kn * 1000.0, "v_y": 0.0, "v_z": 2000.0,
        "m_t": 0.0, "m_y": 3000.0, "m_z": 0.0,
    }])


def _deformations_frame(node_no):
    return pandas.DataFrame([{
        "node_no": node_no,
        "u_x": 0.001, "u_y": 0.0, "u_z": -0.01,
        "phi_x": 0.0, "phi_y": 0.0, "phi_z": 0.0,
    }])


# --- the premise ----------------------------------------------------------

def test_the_ids_really_are_too_big_for_rfem():
    """If stable ids ever became small again, everything below would pass for
    the wrong reason."""
    model = _model()
    assert all(n.id > MAX_RFEM_NUMBER for n in model.nodes)
    assert all(m.id > MAX_RFEM_NUMBER for m in model.members)


# --- reading back ---------------------------------------------------------

def test_a_member_row_lands_on_the_neutral_member():
    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    neutral = model.members[0].id
    rfem_no = backend_map.number_for("member", neutral)

    results = parse_member_internal_forces(
        _forces_frame(rfem_no), load_case_id=1, backend_map=backend_map)

    assert neutral in results
    assert results[neutral][0].axial == pytest.approx(1.0)


def test_a_node_row_lands_on_the_neutral_node():
    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    neutral = model.nodes[1].id
    rfem_no = backend_map.number_for("node", neutral)

    results = parse_node_deformations(
        _deformations_frame(rfem_no), load_case_id=1, backend_map=backend_map)

    assert neutral in results


def test_without_a_map_the_number_is_the_id():
    """Older result files, and the SAF/OpenSees paths, have no map. The
    reader must still work - it just means the two were the same."""
    results = parse_member_internal_forces(_forces_frame(7), load_case_id=1)

    assert 7 in results


def test_a_row_for_an_object_we_did_not_push_is_skipped():
    """The engineer added a member in RFEM by hand. Inventing a neutral id for
    it would attach its forces to one of ours."""
    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))

    results = parse_member_internal_forces(
        _forces_frame(4242), load_case_id=1, backend_map=backend_map)

    assert results == {}


def test_two_members_do_not_swap_results():
    """The failure this guards: reading with the wrong direction silently
    puts member A's forces on member B."""
    model = _model()
    second = stable_id("member", "guid", "s2")
    model.members.append(
        StructuralMember(id=second, node_start=model.nodes[0].id,
                         node_end=model.nodes[1].id, section_id=1))
    backend_map = number_model(model, BackendMap(backend="rfem"))

    first_id = model.members[0].id
    frame = pandas.concat([
        _forces_frame(backend_map.number_for("member", first_id), axial_kn=10.0),
        _forces_frame(backend_map.number_for("member", second), axial_kn=20.0),
    ], ignore_index=True)

    results = parse_member_internal_forces(frame, load_case_id=1, backend_map=backend_map)

    assert results[first_id][0].axial == pytest.approx(10.0)
    assert results[second][0].axial == pytest.approx(20.0)


# --- the full loop --------------------------------------------------------

def test_push_then_read_returns_the_same_objects():
    """One map, both directions, nothing lost in between."""
    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))

    for member in model.members:
        rfem_no = backend_map.number_for("member", member.id)
        assert rfem_no <= MAX_RFEM_NUMBER
        results = parse_member_internal_forces(
            _forces_frame(rfem_no), load_case_id=1, backend_map=backend_map)
        assert list(results) == [member.id]


def test_the_loop_survives_an_edit_between_push_and_read():
    """Push, edit the model, read the old results: they still belong to the
    objects they came from, because the numbers did not move."""
    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    neutral = model.members[0].id
    rfem_no = backend_map.number_for("member", neutral)

    extra = stable_id("node", 8.0, 0.0, 0.0)
    model.nodes.append(StructuralNode(id=extra, point=Point(8, 0, 0)))
    number_model(model, backend_map)

    results = parse_member_internal_forces(
        _forces_frame(rfem_no), load_case_id=1, backend_map=backend_map)

    assert neutral in results
