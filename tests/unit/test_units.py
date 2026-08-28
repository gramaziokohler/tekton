"""The neutral model is metric SI; the translator converts at the boundary.

A millimetre-authored model silently producing 200-metre plates is the failure
this contract exists to prevent.
"""

import pytest
from compas.geometry import Line
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.core.units import UnitError
from compas_timber_fea.core.units import check_section_plausible
from compas_timber_fea.core.units import check_thickness_plausible
from compas_timber_fea.core.units import scale_to_meters
from compas_timber_fea.translator import TimberToStructural


def test_known_units_scale_to_meters():
    assert scale_to_meters("m") == 1.0
    assert scale_to_meters("mm") == 0.001
    assert scale_to_meters("cm") == 0.01


def test_unknown_unit_is_rejected_with_a_useful_message():
    with pytest.raises(UnitError, match="Supported units"):
        scale_to_meters("furlong")


def test_implausible_sections_are_flagged():
    assert check_section_plausible(0.1, 0.2) is None
    assert "below" in check_section_plausible(0.0001, 0.2)
    assert "exceeds" in check_section_plausible(120.0, 240.0)


def test_implausible_thicknesses_are_flagged():
    assert check_thickness_plausible(0.2) is None
    assert "exceeds" in check_thickness_plausible(200.0)
    assert "below" in check_thickness_plausible(0.0002)


def test_thickness_warnings_do_not_repeat_for_float_noise():
    """Two plates differing by float noise must not yield two messages."""
    first = check_thickness_plausible(200.0)
    second = check_thickness_plausible(200.00000000000182)

    assert first == second


def test_millimetre_model_is_converted_to_meters():
    """A 4000 mm beam with a 100x200 mm section becomes 4 m and 0.1x0.2 m."""
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (4000, 0, 0)), width=100, height=200))

    structural_model = TimberToStructural(source_units="mm").translate(model)

    section = structural_model.sections[0]
    assert section.width == pytest.approx(0.1)
    assert section.height == pytest.approx(0.2)

    points = [node.point for node in structural_model.nodes]
    span = max(p.x for p in points) - min(p.x for p in points)
    assert span == pytest.approx(4.0)
    assert structural_model.source_units == "mm"


def test_metre_model_is_left_alone():
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (4, 0, 0)), width=0.1, height=0.2))

    structural_model = TimberToStructural(source_units="m").translate(model)

    section = structural_model.sections[0]
    assert section.width == pytest.approx(0.1)
    assert max(node.point.x for node in structural_model.nodes) == pytest.approx(4.0)


def test_mismatched_unit_declaration_is_reported():
    """A millimetre model declared as metres yields implausible sections."""
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (4000, 0, 0)), width=100, height=200))

    translator = TimberToStructural(source_units="m")
    translator.translate(model)

    assert translator.report, "no warning raised for a 100 m wide timber section"
    assert any("exceeds" in entry for entry in translator.report)


def test_dimensions_differing_only_by_float_noise_share_one_section():
    """CAD geometry carries float noise; it must not split the catalogue."""
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (2, 0, 0)), width=0.1, height=0.2))
    model.add_element(Beam.from_centerline(Line((0, 1, 0), (2, 1, 0)), width=0.1 + 1e-12, height=0.2))

    structural_model = TimberToStructural().translate(model)

    beam_sections = {m.section_id for m in structural_model.members if m.source_element_type == "beam"}
    assert len(beam_sections) == 1
