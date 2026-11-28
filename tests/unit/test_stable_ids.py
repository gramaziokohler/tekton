"""Stable ids: does an untouched beam keep its numbers when the model changes?

Why it matters. The neutral id is the handle everything downstream holds on
to - the RFEM object number, the key a result row is looked up by, the entry a
BackendMap would bind. If adding one beam renumbers the rest, then the next
push cannot tell "this is the same member, updated" from "this is a new
member", and an incremental push is impossible. That is WP6 step 2, and this
file is its acceptance test.

The failure is invisible in a single session, which is why it survived so
long: within one translation the ids are perfectly consistent. It only shows
up across two translations of a model that was edited in between - exactly
what a designer does all day.

What the ids are derived from: the source GUID plus a segment ordinal, never
graph order and never another object's GUID. The second rule is not fussiness -
an earlier design embedded neighbouring GUIDs in an id, and adding a neighbour
re-sorted the set and changed the id of something that had not moved.
"""

from compas.geometry import Line
from compas.geometry import Point

from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from tekton_core.translator import TimberToStructural


def _beam(start, end, width=0.1, height=0.2):
    return Beam.from_centerline(Line(Point(*start), Point(*end)), width=width, height=height)


def _model(beams):
    model = TimberModel()
    for beam in beams:
        model.add_element(beam)
    return model


def _translate(timber_model):
    return TimberToStructural(source_units="m").translate(timber_model)


def _ids_by_guid(structural):
    """{source guid: sorted member ids} - the mapping that has to survive."""
    out = {}
    for member in structural.members:
        if member.source_element_id:
            out.setdefault(member.source_element_id, []).append(member.id)
    return {guid: sorted(ids) for guid, ids in out.items()}


def _node_ids_by_position(structural):
    """{rounded point: node id} - so a moved node is distinguishable from a
    renumbered one."""
    return {
        (round(n.point.x, 6), round(n.point.y, 6), round(n.point.z, 6)): n.id
        for n in structural.nodes
    }


# --- the property the whole work package is about -------------------------

def test_a_beam_added_at_the_end_does_not_renumber_the_others():
    """The benign half: appending happens to leave earlier ids alone, because
    the counter had already passed them. Kept so a regression here is still
    caught."""
    first = _beam((0, 0, 0), (4, 0, 0))
    second = _beam((0, 2, 0), (4, 2, 0))

    before = _ids_by_guid(_translate(_model([first, second])))

    third = _beam((0, 4, 0), (4, 4, 0))
    after = _ids_by_guid(_translate(_model([first, second, third])))

    for guid, ids in before.items():
        assert after[guid] == ids, "beam {} was renumbered".format(guid)


def test_a_beam_added_at_the_front_does_not_renumber_the_others():
    """The acceptance test from WP6, in the form that actually breaks today.

    Appending is harmless by luck. Inserting is not: measured on 2026-10-07,
    adding a beam ahead of two others moved them from (1, 2) to (2, 3). A
    designer does not control which end Grasshopper hands the new beam in at.
    """
    second = _beam((0, 2, 0), (4, 2, 0))
    third = _beam((0, 4, 0), (4, 4, 0))

    before = _ids_by_guid(_translate(_model([second, third])))

    first = _beam((0, 0, 0), (4, 0, 0))
    after = _ids_by_guid(_translate(_model([first, second, third])))

    for guid, ids in before.items():
        assert after[guid] == ids, "beam {} was renumbered".format(guid)


def test_an_added_beam_does_not_move_the_other_nodes():
    first = _beam((0, 0, 0), (4, 0, 0))
    second = _beam((0, 2, 0), (4, 2, 0))

    before = _node_ids_by_position(_translate(_model([first, second])))

    third = _beam((0, 4, 0), (4, 4, 0))
    after = _node_ids_by_position(_translate(_model([first, second, third])))

    for position, node_id in before.items():
        assert after[position] == node_id, "node at {} was renumbered".format(position)


def test_a_removed_beam_does_not_renumber_the_survivors():
    """Deleting is the other half of editing, and the one that shifts ids
    downwards rather than upwards."""
    first = _beam((0, 0, 0), (4, 0, 0))
    second = _beam((0, 2, 0), (4, 2, 0))
    third = _beam((0, 4, 0), (4, 4, 0))

    before = _ids_by_guid(_translate(_model([first, second, third])))
    after = _ids_by_guid(_translate(_model([first, third])))

    for guid in (str(first.guid), str(third.guid)):
        assert after[guid] == before[guid], "beam {} was renumbered".format(guid)


def test_the_order_beams_are_added_in_does_not_change_the_ids():
    """Grasshopper does not promise a stable order between runs. If the id
    depends on it, every re-run looks like an edit."""
    first = _beam((0, 0, 0), (4, 0, 0))
    second = _beam((0, 2, 0), (4, 2, 0))

    forwards = _ids_by_guid(_translate(_model([first, second])))
    backwards = _ids_by_guid(_translate(_model([second, first])))

    assert forwards == backwards


def test_translating_the_same_model_twice_gives_the_same_ids():
    """The weakest form of the property, and the one that must never fail."""
    beams = [_beam((0, 0, 0), (4, 0, 0)), _beam((0, 2, 0), (4, 2, 0))]

    assert _ids_by_guid(_translate(_model(beams))) == _ids_by_guid(_translate(_model(beams)))


def test_one_translator_used_twice_does_not_keep_counting():
    """The member counter lives on the instance and was never reset in
    translate(), so a reused translator numbered the second model's members
    starting after the first model's."""
    beams = [_beam((0, 0, 0), (4, 0, 0)), _beam((0, 2, 0), (4, 2, 0))]
    translator = TimberToStructural(source_units="m")

    first = _ids_by_guid(translator.translate(_model(beams)))
    second = _ids_by_guid(translator.translate(_model(beams)))

    assert first == second


# --- what the ids are made of --------------------------------------------

def test_a_member_id_is_derived_from_its_source_beam():
    """Not from position in a list. Two models containing only that beam,
    built in different surroundings, give it the same id."""
    beam = _beam((0, 0, 0), (4, 0, 0))
    other = _beam((10, 10, 0), (14, 10, 0))

    alone = _ids_by_guid(_translate(_model([beam])))
    crowded = _ids_by_guid(_translate(_model([other, beam])))

    assert crowded[str(beam.guid)] == alone[str(beam.guid)]


def test_ids_stay_positive_integers():
    """RFEM object numbers are 1-based positive integers, and the neutral id
    is pushed straight into them."""
    structural = _translate(_model([_beam((0, 0, 0), (4, 0, 0))]))

    assert all(isinstance(m.id, int) and m.id > 0 for m in structural.members)
    assert all(isinstance(n.id, int) and n.id > 0 for n in structural.nodes)


def test_ids_are_unique_within_a_model():
    beams = [_beam((0, i, 0), (4, i, 0)) for i in range(5)]
    structural = _translate(_model(beams))

    member_ids = [m.id for m in structural.members]
    node_ids = [n.id for n in structural.nodes]

    assert len(member_ids) == len(set(member_ids))
    assert len(node_ids) == len(set(node_ids))


def test_a_node_shared_by_two_beams_has_one_id():
    """Two beams meeting at a point share the node - that is what makes the
    structure connected rather than two loose pieces."""
    structural = _translate(_model([
        _beam((0, 0, 0), (4, 0, 0)),
        _beam((4, 0, 0), (4, 4, 0)),
    ]))

    at_corner = [n for n in structural.nodes
                 if abs(n.point.x - 4) < 1e-6 and abs(n.point.y) < 1e-6 and abs(n.point.z) < 1e-6]
    assert len(at_corner) == 1


def test_source_node_id_is_real_provenance_not_the_index():
    """It used to store str(graph index), which changes exactly when `id`
    changes - a provenance field that provided no provenance."""
    structural = _translate(_model([_beam((0, 0, 0), (4, 0, 0))]))

    for node in structural.nodes:
        if node.source_node_id is not None:
            assert node.source_node_id != str(node.id), (
                "source_node_id is just the id again, so it anchors nothing")


# --- the rule a previous design died on -----------------------------------

def test_an_id_never_embeds_another_elements_guid():
    """From the design review's list of rejected ideas: an id built from a
    growing set of neighbouring GUIDs flips when a neighbour sorts lower, and
    the BackendMap then binds the wrong object."""
    first = _beam((0, 0, 0), (4, 0, 0))
    second = _beam((4, 0, 0), (4, 4, 0))

    structural = _translate(_model([first, second]))
    guids = {str(first.guid), str(second.guid)}

    for member in structural.members:
        own = member.source_element_id
        foreign = guids - {own}
        for other in foreign:
            assert other not in str(member.id), "member id contains a foreign guid"
            if member.source_segment_id:
                assert other not in str(member.source_segment_id), (
                    "segment id contains a foreign guid")


def test_a_neighbour_appearing_does_not_change_an_id():
    """The concrete form of the rule above: connect a second beam to the
    first, and the first must keep its numbers."""
    first = _beam((0, 0, 0), (4, 0, 0))
    before = _ids_by_guid(_translate(_model([first])))

    second = _beam((4, 0, 0), (4, 4, 0))
    after = _ids_by_guid(_translate(_model([first, second])))

    assert after[str(first.guid)] == before[str(first.guid)]


# --- on a real model ------------------------------------------------------

def test_the_sticks_model_survives_a_deleted_beam():
    """The measurement that justifies the work package.

    84 beams, 344 nodes, 404 members. Delete one beam and translate again:
    under graph-order numbering **83 of the 83 surviving beams** were
    renumbered, which is every object a BackendMap could have bound. The
    property is that none of them are.
    """
    from compas.data import json_load

    def by_guid(structural):
        out = {}
        for member in structural.members:
            if member.source_element_id:
                out.setdefault(member.source_element_id, []).append(member.id)
        return {guid: sorted(ids) for guid, ids in out.items()}

    def node_ids(structural):
        return {
            (round(n.point.x, 6), round(n.point.y, 6), round(n.point.z, 6)): n.id
            for n in structural.nodes
        }

    path = "tests/timber_model_sticks.json"
    full = TimberToStructural(source_units="mm").translate(json_load(path))

    reduced_model = json_load(path)
    reduced_model.remove_element(list(reduced_model.beams)[0])
    reduced = TimberToStructural(source_units="mm").translate(reduced_model)

    before, after = by_guid(full), by_guid(reduced)
    shared = set(before) & set(after)
    assert len(shared) == 83, "fixture changed shape"
    assert [guid for guid in shared if before[guid] != after[guid]] == []

    before_nodes, after_nodes = node_ids(full), node_ids(reduced)
    for position in set(before_nodes) & set(after_nodes):
        assert before_nodes[position] == after_nodes[position]


def test_the_sticks_model_translates_identically_twice():
    from compas.data import json_load

    path = "tests/timber_model_sticks.json"
    first = TimberToStructural(source_units="mm").translate(json_load(path))
    second = TimberToStructural(source_units="mm").translate(json_load(path))

    assert [m.id for m in first.members] == [m.id for m in second.members]
    assert [n.id for n in first.nodes] == [n.id for n in second.nodes]


def test_ids_stay_inside_what_rfem_accepts():
    """The neutral id is pushed straight into an RFEM object number, which is
    a signed 32-bit integer."""
    from compas.data import json_load

    structural = TimberToStructural(source_units="mm").translate(
        json_load("tests/timber_model_sticks.json"))

    for item in list(structural.members) + list(structural.nodes):
        assert 0 < item.id <= 2_147_483_647
