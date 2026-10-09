"""Neutral ids are translated at the backend boundary, in both directions.

The push writes RFEM's own dense numbers, not our hash-derived neutral ids, and
the result reader turns RFEM's numbers back into neutral ids. The two have to
move together: a half-converted chain attaches results to the wrong objects
without anything failing, which is the worst shape a bug can take here.

These tests exercise the translation itself rather than the protobuf messages,
so they run without `dlubal-api` installed. `test_dlubal_mappers.py` covers the
proto side when the package is available.
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


def _model():
    """A model whose ids are the real thing: hashes, far above RFEM's ceiling."""
    model = StructuralModel()
    model.materials[1] = "C24"
    a = stable_id("node", 0.0, 0.0, 0.0)
    b = stable_id("node", 4.0, 0.0, 0.0)
    model.nodes.append(StructuralNode(id=a, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=b, point=Point(4, 0, 0)))
    model.sections.append(StructuralSection(id=1, name="R", material_id=1, width=0.1, height=0.2))
    model.members.append(
        StructuralMember(id=stable_id("member", "guid", "seg"), node_start=a, node_end=b, section_id=1)
    )
    model.supports.append(StructuralSupport(id=1, nodes=[a]))
    return model


def test_the_fixture_really_exceeds_what_rfem_accepts():
    """Guards the premise: if stable ids ever became small again, the rest of
    this file would pass for the wrong reason."""
    model = _model()
    assert all(n.id > MAX_RFEM_NUMBER for n in model.nodes)
    assert all(m.id > MAX_RFEM_NUMBER for m in model.members)


# --- numbering a whole model ---------------------------------------------

def test_numbering_a_model_puts_everything_inside_the_ceiling():
    from compas_dlubal.dlubal.numbering import number_model

    backend_map = number_model(_model(), BackendMap(backend="rfem"))

    for category in ("node", "member", "support"):
        for number in (backend_map.assigned.get(category) or {}).values():
            assert 0 < number <= MAX_RFEM_NUMBER


def test_numbering_is_dense_from_one():
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    model.nodes.append(StructuralNode(id=stable_id("node", 8.0, 0.0, 0.0), point=Point(8, 0, 0)))

    backend_map = number_model(model, BackendMap(backend="rfem"))

    assert sorted((backend_map.assigned["node"]).values()) == [1, 2, 3]


def test_numbering_twice_does_not_renumber():
    """An unchanged model pushed twice must keep every number, or the second
    push replaces objects the engineer has been working on."""
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    before = dict(backend_map.assigned["node"])

    number_model(model, backend_map)

    assert backend_map.assigned["node"] == before


def test_an_edited_model_keeps_the_numbers_of_what_survived():
    """The whole point of WP6: add an element, and everything else stays put."""
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    before = dict(backend_map.assigned["node"])

    extra = stable_id("node", 8.0, 0.0, 0.0)
    model.nodes.append(StructuralNode(id=extra, point=Point(8, 0, 0)))
    number_model(model, backend_map)

    for neutral, number in before.items():
        assert backend_map.assigned["node"][neutral] == number
    assert backend_map.assigned["node"][str(extra)] not in before.values()


# --- the member's endpoints must be translated too ------------------------

def test_a_members_endpoints_are_backend_numbers_not_neutral_ids():
    """The subtle half. Writing a small `no` while leaving `node_start` as a
    hash would produce a member pointing at a node that does not exist."""
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    member = model.members[0]

    start = backend_map.number_for("node", member.node_start)
    end = backend_map.number_for("node", member.node_end)

    assert start <= MAX_RFEM_NUMBER and end <= MAX_RFEM_NUMBER
    assert start != end


def test_a_support_points_at_backend_node_numbers():
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))

    for neutral in model.supports[0].nodes:
        assert backend_map.number_for("node", neutral) <= MAX_RFEM_NUMBER


# --- reading results back -------------------------------------------------

def test_a_result_row_lands_on_the_neutral_member():
    """RFEM reports member 1; the result has to end up on the neutral member,
    whatever its id is."""
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    neutral = model.members[0].id
    rfem_number = backend_map.number_for("member", neutral)

    assert backend_map.neutral_for("member", rfem_number) == neutral


def test_a_row_for_an_object_we_did_not_push_is_not_invented():
    """The engineer added a member in RFEM. It has no neutral counterpart, and
    pretending it does would attach its forces to one of ours."""
    from compas_dlubal.dlubal.numbering import number_model

    backend_map = number_model(_model(), BackendMap(backend="rfem"))

    assert backend_map.neutral_for("member", 9999) is None


def test_the_round_trip_is_exact_for_every_object():
    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))

    for node in model.nodes:
        number = backend_map.number_for("node", node.id)
        assert backend_map.neutral_for("node", number) == node.id
    for member in model.members:
        number = backend_map.number_for("member", member.id)
        assert backend_map.neutral_for("member", number) == member.id


# --- persistence across sessions -----------------------------------------

def test_the_numbering_survives_a_session():
    """An incremental push happens in a later session than the one that
    created the objects, so the map has to come back off disk intact."""
    import os
    import tempfile

    from compas_dlubal.dlubal.numbering import number_model

    model = _model()
    backend_map = number_model(model, BackendMap(backend="rfem"))
    before = dict(backend_map.assigned["member"])

    path = os.path.join(tempfile.mkdtemp(), "m.backend.json")
    backend_map.save(path)

    restored = number_model(model, BackendMap.load(path, backend="rfem"))
    assert restored.assigned["member"] == before


def test_the_map_path_sits_next_to_the_model():
    """Findable without being told where it is."""
    from compas_dlubal.dlubal.numbering import map_path_for

    assert map_path_for("/tmp/x/model.json") == "/tmp/x/model.rfem.json"
    assert map_path_for("/tmp/x/model.json", backend="saf") == "/tmp/x/model.saf.json"


def test_numbering_refuses_a_map_from_another_backend():
    import os
    import tempfile

    from compas_dlubal.dlubal.numbering import number_model

    backend_map = number_model(_model(), BackendMap(backend="rfem"))
    path = os.path.join(tempfile.mkdtemp(), "m.json")
    backend_map.save(path)

    with pytest.raises(ValueError, match="backend"):
        BackendMap.load(path, backend="opensees")
