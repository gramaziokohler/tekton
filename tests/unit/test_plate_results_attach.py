"""WP5b: analysis results back onto the timber plates.

The decision under test is the sampling: a plate sample is a **point**, not a
UV pair. A UV would need a parametrisation the neutral model does not carry
and that changes when someone reorders the outline - the numbers would move
without anyone noticing. A point survives a reordered outline, a remesh and
a change of backend, because none of them move the plate.
"""

import pytest

from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.materials import Material
from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralSurfaceResult
from compas_timber_fea.core.model import StructuralThickness
from compas_timber_fea.results import ANALYSIS_KEY
from compas_timber_fea.results import attach_plate_results_to_timber

GUID = "plate-guid-1"


class FakePlate:
    def __init__(self, guid=GUID):
        self.guid = guid
        self.attributes = {}


class FakeTimberModel:
    def __init__(self, *plates):
        self.plates = list(plates)
        self.beams = []


def structural(samples=None, surface_guid=GUID, surface_id=1):
    model = StructuralModel()
    model.nodes = [StructuralNode(id=i, point=Point(x, y, 0))
                   for i, (x, y) in enumerate([(0, 0), (4, 0), (4, 3), (0, 3)], start=1)]
    model.materials = {1: Material.resolve("C24")}
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.2)]
    model.surfaces = [StructuralSurface(id=surface_id, nodes=[1, 2, 3, 4], thickness_id=1,
                                        source_element_id=surface_guid)]
    model.load_cases = [StructuralLoadCase(id=1, name="G")]
    result_set = StructuralResultSet(load_case_id=1, name="G")
    result_set.surface_results = {surface_id: samples if samples is not None else [
        StructuralSurfaceResult(surface_id=surface_id, load_case_id=1, position=Point(1, 1, 0),
                                moment_x=3.0, moment_y=1.0, displacement=Vector(0, 0, -0.004)),
        StructuralSurfaceResult(surface_id=surface_id, load_case_id=1, position=Point(2, 2, 0),
                                moment_x=-5.0, moment_y=2.0, displacement=Vector(0, 0, -0.009)),
    ]}
    model.results = {1: result_set}
    return model


def analysis_of(plate):
    return plate.attributes[ANALYSIS_KEY]


def first_case(plate):
    return next(iter(analysis_of(plate)["load_cases"].values()))


# --- the mapping ---------------------------------------------------------

def test_results_reach_the_plate_through_its_guid():
    plate = FakePlate()
    written = attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    assert list(written) == [GUID]
    assert ANALYSIS_KEY in plate.attributes


def test_a_plate_the_results_do_not_name_stays_untouched():
    plate = FakePlate("some-other-plate")
    written = attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    assert written == {}
    assert plate.attributes == {}


def test_a_model_without_plates_yields_nothing():
    assert attach_plate_results_to_timber(structural(), FakeTimberModel()) == {}


def test_a_model_without_results_yields_nothing():
    model = structural()
    model.results = {}
    assert attach_plate_results_to_timber(model, FakeTimberModel(FakePlate())) == {}


# --- the samples ---------------------------------------------------------

def test_a_sample_is_a_point_not_a_parameter():
    """The whole design decision, asserted: 3 coordinates, not one or two."""
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    point, values = first_case(plate)["samples"][0]
    assert len(point) == 3
    assert all(isinstance(c, float) for c in point)
    assert "m_x" in values


def test_samples_keep_every_plate_quantity():
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    _point, values = first_case(plate)["samples"][0]
    for key in ("m_x", "m_y", "m_xy", "n_x", "n_y", "n_xy"):
        assert key in values


def test_displacement_travels_as_a_plain_tuple():
    """plate.attributes has to stay JSON-plain - a Vector does not survive."""
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    _point, values = first_case(plate)["samples"][0]
    assert isinstance(values["displacement"], tuple)
    assert all(isinstance(c, float) for c in values["displacement"])


def test_samples_are_ordered_so_two_runs_agree():
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    points = [point for point, _values in first_case(plate)["samples"]]
    assert points == sorted(points)


def test_a_sample_without_a_position_is_skipped():
    samples = [StructuralSurfaceResult(surface_id=1, load_case_id=1, position=None, moment_x=3.0)]
    plate = FakePlate()
    assert attach_plate_results_to_timber(structural(samples), FakeTimberModel(plate)) == {}


# --- the envelope --------------------------------------------------------

def test_the_envelope_keeps_the_sign_of_the_largest_value():
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    assert first_case(plate)["envelope"]["m_x"] == pytest.approx(-5.0)
    assert first_case(plate)["envelope"]["m_y"] == pytest.approx(2.0)


# --- provenance ----------------------------------------------------------

def test_provenance_records_the_load_cases_and_the_axis_caveat():
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    provenance = analysis_of(plate)["provenance"]
    assert provenance["load_cases"] == [1]
    assert provenance["source"] == "tekton"
    assert "plate axes" in provenance["axes"]


# --- utilisation ---------------------------------------------------------

def test_utilisation_is_written_where_it_was_computed():
    from compas_timber_fea.design import DesignAssumptions
    from compas_timber_fea.design.plates import check_plates

    model = structural()
    plate = FakePlate()
    attach_plate_results_to_timber(
        model, FakeTimberModel(plate), plate_checks=check_plates(model, DesignAssumptions()))
    values = dict(first_case(plate)["samples"])[(2.0, 2.0, 0.0)]
    assert values["utilization"] > 0
    assert values["governing_check"] == "bending x"


def test_without_checks_no_utilisation_is_invented():
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    _point, values = first_case(plate)["samples"][0]
    assert "utilization" not in values


def test_the_envelope_carries_the_governing_check():
    from compas_timber_fea.design import DesignAssumptions
    from compas_timber_fea.design.plates import check_plates

    model = structural()
    plate = FakePlate()
    attach_plate_results_to_timber(
        model, FakeTimberModel(plate), plate_checks=check_plates(model, DesignAssumptions()))
    envelope = first_case(plate)["envelope"]
    assert envelope["utilization"] > 0
    assert envelope["governing_check"] == "bending x"


# --- the same shape beams use -------------------------------------------

def test_the_analysis_dict_has_the_shape_beam_results_have():
    """Anything that reads a beam's analysis must be able to read a plate's."""
    plate = FakePlate()
    attach_plate_results_to_timber(structural(), FakeTimberModel(plate))
    analysis = analysis_of(plate)
    assert set(analysis) == {"provenance", "load_cases"}
    case = first_case(plate)
    assert set(case) == {"samples", "envelope"}
