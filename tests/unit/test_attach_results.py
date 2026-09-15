"""Results flow: neutral model is the system of record, the timber model gets a view.

The reader fills ``structural_model.results`` (agnostic, serialized with the
model). ``attach_results_to_timber`` then projects those results onto the
design model as (t, values) samples plus an envelope per beam - the beam knows
nothing about how FEA segmented it, and doesn't need to.
"""

import pytest
from compas.geometry import Line
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.results import ANALYSIS_KEY
from compas_timber_fea.results import attach_results_to_timber
from compas_timber_fea.translator import TimberToStructural


@pytest.fixture
def translated():
    """A continuous beam with a post butting into its middle, so the beam splits."""
    from compas_timber.connections import TButtJoint

    model = TimberModel()
    beam = Beam.from_centerline(Line((0, 0, 0), (4, 0, 0)), width=0.1, height=0.2)
    post = Beam.from_centerline(Line((2, 0, -3), (2, 0, 0)), width=0.1, height=0.1)
    model.add_element(beam)
    model.add_element(post)
    TButtJoint.create(model, post, beam)
    structural_model = TimberToStructural().translate(model)
    return model, structural_model, beam


def _fill_results(structural_model, beam_guid):
    """Synthetic member results: axial -5 everywhere, peak moment mid-member."""
    member_results = {}
    for member in structural_model.members:
        if member.source_element_id != str(beam_guid):
            continue
        member_results[member.id] = [
            StructuralMemberResult(member_id=member.id, load_case_id=1, position=0.0, axial=-5.0, moment_y=0.0),
            StructuralMemberResult(member_id=member.id, load_case_id=1, position=0.5, axial=-5.0, moment_y=2.5),
            StructuralMemberResult(member_id=member.id, load_case_id=1, position=1.0, axial=-5.0, moment_y=0.0),
        ]
    structural_model.results[1] = StructuralResultSet(load_case_id=1, name="LC1", member_results=member_results)


def test_results_land_on_the_beam(translated):
    timber_model, structural_model, beam = translated
    _fill_results(structural_model, beam.guid)

    attached = attach_results_to_timber(structural_model, timber_model)

    assert str(beam.guid) in attached
    analysis = beam.attributes[ANALYSIS_KEY]
    assert 1 in analysis["load_cases"]
    assert analysis["provenance"]["load_cases"] == [1]


def test_samples_use_beam_parameters_not_member_parameters(translated):
    """The beam splits at x=2; member-mid positions must map to beam params, not 0.5."""
    timber_model, structural_model, beam = translated
    beam_members = [m for m in structural_model.members if m.source_element_id == str(beam.guid)]
    assert len(beam_members) >= 2, "fixture should split the beam"

    _fill_results(structural_model, beam.guid)
    attach_results_to_timber(structural_model, timber_model)

    samples = beam.attributes[ANALYSIS_KEY]["load_cases"][1]["samples"]
    params = [t for t, _values in samples]
    # Segment [0,2] mid = beam param 0.25; segment [2,4] mid = 0.75.
    assert 0.25 in params
    assert 0.75 in params
    assert all(0.0 <= t <= 1.0 for t in params)


def test_envelope_keeps_the_signed_extreme(translated):
    timber_model, structural_model, beam = translated
    _fill_results(structural_model, beam.guid)

    attach_results_to_timber(structural_model, timber_model)

    envelope = beam.attributes[ANALYSIS_KEY]["load_cases"][1]["envelope"]
    assert envelope["N"] == -5.0, "sign must survive - compression is not tension"
    assert envelope["My"] == 2.5


def test_displacement_travels_as_plain_tuple(translated):
    """Member deformations reach the beam, JSON-plain, with the largest one in the envelope."""
    from compas.geometry import Vector

    timber_model, structural_model, beam = translated
    _fill_results(structural_model, beam.guid)
    rows = next(iter(structural_model.results[1].member_results.values()))
    rows[1].displacement = Vector(0.0, 0.0, -0.012)
    rows[0].displacement = Vector(0.0, 0.0, 0.0)

    attach_results_to_timber(structural_model, timber_model)

    case = beam.attributes[ANALYSIS_KEY]["load_cases"][1]
    with_displacement = [values["displacement"] for _t, values in case["samples"] if "displacement" in values]
    assert (0.0, 0.0, -0.012) in with_displacement
    assert all(isinstance(d, tuple) for d in with_displacement)
    assert case["envelope"]["displacement"] == (0.0, 0.0, -0.012)


def test_beams_without_results_stay_untouched(translated):
    timber_model, structural_model, beam = translated
    post = next(b for b in timber_model.beams if b is not beam)
    _fill_results(structural_model, beam.guid)

    attach_results_to_timber(structural_model, timber_model)

    assert ANALYSIS_KEY not in post.attributes


def test_no_results_is_a_noop(translated):
    timber_model, structural_model, beam = translated

    assert attach_results_to_timber(structural_model, timber_model) == {}
    assert ANALYSIS_KEY not in beam.attributes


def test_results_survive_model_serialization(translated, tmp_path):
    """The neutral model is the system of record - results serialize with it."""
    _timber_model, structural_model, beam = translated
    _fill_results(structural_model, beam.guid)

    path = tmp_path / "with_results.json"
    structural_model.to_json(path)
    loaded = StructuralModel.from_json(path)

    assert 1 in loaded.results
    result_set = loaded.results[1]
    assert result_set.member_results, "member results were lost"
    any_member = next(iter(result_set.member_results.values()))
    assert any_member[1].moment_y == 2.5
