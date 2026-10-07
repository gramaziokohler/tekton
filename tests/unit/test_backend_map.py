"""The BackendMap: neutral id on one side, a backend's own number on the other.

Why the two must not be the same number. Until now `no = member.id`, 1:1 in
both directions - the push wrote the neutral id into RFEM's object number and
`result_parsing` read the RFEM table number straight back as a neutral id.
That works only while every run rebuilds the model from scratch, and it forces
the neutral id to satisfy a backend's constraints.

Two things make it untenable:

* **RFEM's numbers are small.** Dlubal document 999,999 objects per category
  for RFEM 6 and RSTAB 9 (RFEM 5 was 99,999), and the proto field is a
  *signed* int32. Our stable ids are hashes spread over 2^31 - measured on the
  sticks model, all 748 of them exceed 99,999 and 747 exceed 999,999. Pushing
  them directly is outside the documented capacity.
* **An incremental push needs the backend to keep its numbers.** The engineer's
  model has object 17; our next push has to recognise it as the same member,
  not create a second one.

So the neutral id stays what it is - derived from the source GUID, stable
across edits, never touched by a backend - and each backend gets a compact
numbering of its own, remembered next to the model. One map per backend,
because RFEM's numbers are not SAF's names and not OpenSees' tags.
"""

import json
import os
import tempfile

import pytest

from compas_timber_fea.core.backend_map import BackendMap
from compas_timber_fea.core.backend_map import MAX_RFEM_NUMBER


def _map():
    return BackendMap(backend="rfem")


# --- allocation -----------------------------------------------------------

def test_the_first_number_is_one():
    """Dlubal does not do zero-based numbering."""
    assert _map().number_for("node", 143193) == 1


def test_numbers_are_dense():
    """The point of the exercise: whatever the neutral ids look like, the
    backend sees 1, 2, 3."""
    backend_map = _map()
    numbers = [backend_map.number_for("node", nid) for nid in (143193, 2144069882, 29474)]
    assert numbers == [1, 2, 3]


def test_asking_twice_gives_the_same_number():
    backend_map = _map()
    first = backend_map.number_for("member", 500)
    assert backend_map.number_for("member", 500) == first


def test_each_category_numbers_from_one_separately():
    """RFEM counts nodes, members and surfaces in separate namespaces, so a
    node and a member may both be number 1."""
    backend_map = _map()
    assert backend_map.number_for("node", 10) == 1
    assert backend_map.number_for("member", 10) == 1
    assert backend_map.number_for("surface", 10) == 1


def test_a_huge_neutral_id_becomes_a_small_number():
    """The regression this exists to fix."""
    backend_map = _map()
    assert backend_map.number_for("node", 2_147_471_814) <= MAX_RFEM_NUMBER


def test_every_allocated_number_stays_inside_the_documented_capacity():
    backend_map = _map()
    for i in range(1000):
        number = backend_map.number_for("node", 1_000_000 + i * 7919)
        assert 0 < number <= MAX_RFEM_NUMBER


def test_running_out_of_numbers_is_an_error_not_a_wraparound():
    """Silently wrapping past the ceiling would overwrite an existing object -
    Dlubal confirm that re-using a number overwrites the former object."""
    backend_map = BackendMap(backend="rfem", _limit=3)
    for i in range(3):
        backend_map.number_for("node", i)
    with pytest.raises(ValueError, match="numbers"):
        backend_map.number_for("node", 99)


# --- reading back ---------------------------------------------------------

def test_a_backend_number_resolves_to_its_neutral_id():
    """What `result_parsing` needs: a result row names RFEM's number, and the
    result has to land on the right neutral object."""
    backend_map = _map()
    neutral = 2_144_069_882
    number = backend_map.number_for("member", neutral)

    assert backend_map.neutral_for("member", number) == neutral


def test_an_unknown_backend_number_resolves_to_nothing():
    """An object the engineer added in RFEM has no neutral counterpart. That
    is information, not an error - it is exactly what the read-back step
    (WP6 step 5) will look for."""
    assert _map().neutral_for("member", 42) is None


def test_the_two_directions_agree_for_everything_allocated():
    backend_map = _map()
    neutral_ids = [143193, 2144069882, 29474, 7, 999999999]
    for neutral in neutral_ids:
        number = backend_map.number_for("node", neutral)
        assert backend_map.neutral_for("node", number) == neutral


# --- persistence ----------------------------------------------------------

def test_it_survives_a_round_trip_through_disk():
    """Without this the map is useless: an incremental push happens in a
    later session than the one that created the objects."""
    backend_map = _map()
    backend_map.number_for("node", 143193)
    backend_map.number_for("member", 2144069882)

    path = os.path.join(tempfile.mkdtemp(), "model.backend.json")
    backend_map.save(path)
    restored = BackendMap.load(path)

    assert restored.backend == "rfem"
    assert restored.number_for("node", 143193) == 1
    assert restored.number_for("member", 2144069882) == 1


def test_reloading_does_not_hand_out_a_used_number_again():
    """The allocator has to resume where it left off, or the second session
    overwrites the first session's objects."""
    backend_map = _map()
    for neutral in (10, 20, 30):
        backend_map.number_for("node", neutral)

    path = os.path.join(tempfile.mkdtemp(), "m.json")
    backend_map.save(path)
    restored = BackendMap.load(path)

    assert restored.number_for("node", 40) == 4


def test_a_missing_file_loads_as_an_empty_map():
    """First push of a model: there is nothing to resume from, and that is
    normal rather than an error."""
    path = os.path.join(tempfile.mkdtemp(), "nothing-here.json")
    backend_map = BackendMap.load(path, backend="rfem")

    assert backend_map.backend == "rfem"
    assert backend_map.number_for("node", 1) == 1


def test_the_file_is_readable_json():
    """An engineer debugging a push should be able to open it."""
    backend_map = _map()
    backend_map.number_for("node", 143193)

    path = os.path.join(tempfile.mkdtemp(), "m.json")
    backend_map.save(path)

    with open(path) as handle:
        data = json.load(handle)
    assert data["backend"] == "rfem"
    assert "node" in data["assigned"]


def test_loading_a_map_for_the_wrong_backend_is_refused():
    """RFEM's numbers are not SAF's. Mixing them would bind results to the
    wrong objects, silently."""
    backend_map = _map()
    path = os.path.join(tempfile.mkdtemp(), "m.json")
    backend_map.save(path)

    with pytest.raises(ValueError, match="backend"):
        BackendMap.load(path, backend="saf")


# --- what it is for: the incremental push ---------------------------------

def test_an_object_that_survives_an_edit_keeps_its_backend_number():
    """Push, edit the model, push again: the untouched member is still RFEM
    object 2, so the second push can update it instead of creating a twin."""
    backend_map = _map()
    first_push = [143193, 2144069882, 29474]
    numbers = {nid: backend_map.number_for("member", nid) for nid in first_push}

    # The middle member was deleted, a new one added. The stable ids of the
    # survivors are unchanged - that is WP6 step 2.
    second_push = [143193, 29474, 777777]
    after = {nid: backend_map.number_for("member", nid) for nid in second_push}

    assert after[143193] == numbers[143193]
    assert after[29474] == numbers[29474]
    assert after[777777] not in numbers.values()


def test_a_deleted_object_does_not_free_its_number_for_reuse():
    """Reusing it would silently overwrite whatever the engineer did with the
    old object. The gap is cheap; the confusion is not."""
    backend_map = _map()
    backend_map.number_for("node", 1)
    second = backend_map.number_for("node", 2)
    backend_map.number_for("node", 3)

    backend_map.forget("node", 2)
    assert backend_map.number_for("node", 99) != second


def test_what_is_gone_can_be_listed():
    """The incremental push needs the difference: which backend objects
    belong to neutral ids that no longer exist."""
    backend_map = _map()
    for neutral in (10, 20, 30):
        backend_map.number_for("node", neutral)

    stale = backend_map.obsolete("node", {10, 30})
    assert stale == [backend_map.number_for("node", 20)]
