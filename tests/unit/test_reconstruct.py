"""Structural -> Timber: the beams come back exactly, results included.

The neutral model keeps everything a beam body needs (segments per source
GUID, section, orientation), so a StructuralModel on its own - loaded from
JSON, handed back by an engineer - becomes a TimberModel again. Joint types
are not in the neutral model and are not expected back.
"""

import pytest
from compas.data import json_load
from compas.geometry import Line
from compas.geometry import Vector
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.reconstruct import beam_connectivity
from compas_timber_fea.reconstruct import chain_endpoints
from compas_timber_fea.reconstruct import structural_to_timber
from compas_timber_fea.translator import TimberToStructural

STICKS = "tests/timber_model_sticks.json"


@pytest.fixture
def sticks():
    return json_load(STICKS)


def test_beams_come_back_with_guid_geometry_and_section(sticks):
    structural = TimberToStructural().translate(sticks)

    rebuilt, report = structural_to_timber(structural)

    original = {str(b.guid): b for b in sticks.beams}
    assert len(list(rebuilt.beams)) == len(original)
    for beam in rebuilt.beams:
        source = original[str(beam.guid)]  # KeyError here = GUID not restored
        assert beam.length == pytest.approx(source.length, abs=1e-6)
        assert beam.width == pytest.approx(source.width) and beam.height == pytest.approx(source.height)
        assert beam.frame.xaxis.dot(source.frame.xaxis) == pytest.approx(1.0, abs=1e-6)
        assert beam.frame.zaxis.dot(source.frame.zaxis) == pytest.approx(1.0, abs=1e-6)
    assert any("84 beams rebuilt" in line for line in report)


def test_split_beam_is_one_beam_again():
    """A post butting into a beam splits it into two members; the rebuild must not yield two beams."""
    from compas_timber.connections import TButtJoint

    model = TimberModel()
    beam = Beam.from_centerline(Line((0, 0, 0), (4, 0, 0)), width=0.1, height=0.2)
    post = Beam.from_centerline(Line((2, 0, -3), (2, 0, 0)), width=0.1, height=0.1)
    model.add_element(beam)
    model.add_element(post)
    TButtJoint.create(model, post, beam)
    structural = TimberToStructural().translate(model)
    assert sum(1 for m in structural.members if m.source_element_id == str(beam.guid)) >= 2

    rebuilt, _ = structural_to_timber(structural)

    beams = {str(b.guid): b for b in rebuilt.beams}
    assert set(beams) == {str(beam.guid), str(post.guid)}
    assert beams[str(beam.guid)].length == pytest.approx(4.0)


def test_units_are_scaled_back_to_source_units():
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (3000, 0, 0)), width=100, height=200))
    structural = TimberToStructural(source_units="mm").translate(model)
    assert structural.sections[0].width == pytest.approx(0.1)  # metres inside

    rebuilt, _ = structural_to_timber(structural)

    beam = next(iter(rebuilt.beams))
    assert beam.length == pytest.approx(3000.0)
    assert beam.width == pytest.approx(100.0)


def test_results_ride_along(sticks):
    structural = TimberToStructural().translate(sticks)
    member = next(m for m in structural.members if m.member_type == "BEAM")
    structural.results[1] = StructuralResultSet(
        load_case_id=1,
        member_results={member.id: [StructuralMemberResult(member_id=member.id, load_case_id=1, position=0.5, axial=-3.0, displacement=Vector(0, 0, -0.01))]},
    )

    rebuilt, report = structural_to_timber(structural)

    beam = next(b for b in rebuilt.beams if str(b.guid) == member.source_element_id)
    envelope = beam.attributes["analysis"]["load_cases"][1]["envelope"]
    assert envelope["N"] == -3.0
    assert envelope["displacement"] == (0.0, 0.0, -0.01)
    assert any("results attached to 1" in line for line in report)


def test_connectivity_lists_each_beam_pair_once(sticks):
    structural = TimberToStructural().translate(sticks)

    connections = beam_connectivity(structural)

    pairs = [(a, b) for a, b, _joint in connections]
    assert len(pairs) == len(set(pairs))
    assert all(a != b for a, b in pairs)
    assert len(connections) > 0


def test_chain_endpoints_follow_member_direction():
    class M:
        def __init__(self, id, s, e):
            self.id, self.node_start, self.node_end = id, s, e

    assert chain_endpoints([M(2, 5, 9), M(1, 3, 5), M(3, 9, 12)]) == (3, 12)


def test_structural_model_alone_is_enough(sticks, tmp_path):
    """The point of it: no timber model in hand, only the JSON the worker left behind."""
    path = tmp_path / "structural.json"
    TimberToStructural().translate(sticks).to_json(path)

    rebuilt, _ = structural_to_timber(StructuralModel.from_json(path))

    assert len(list(rebuilt.beams)) == 84
