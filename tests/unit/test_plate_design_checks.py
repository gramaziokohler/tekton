"""EC5 checks for plates, from the shell results.

The reference is a hand calculation on a one-metre strip, written out so a
reader can follow it. A C24 plate 200 mm thick, service class 1, medium-term:

    A     = 1.0 * 0.200          = 0.200 m2/m
    W     = 1.0 * 0.200^2 / 6    = 0.006667 m3/m
    f_md  = 0.8 * 24 / 1.3       = 14.769 MPa = 14769 kN/m2

The scope limit is tested as hard as the arithmetic: these checks assume a
homogeneous isotropic slab, which is wrong for CLT, and every result has to
say so. A silent number here would be unconservative in the weak direction.
"""

import pytest

from compas.geometry import Point

from tekton_core.core.materials import Material
from tekton_core.core.model import StructuralLoadCase
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralResultSet
from tekton_core.core.model import StructuralSurface
from tekton_core.core.model import StructuralSurfaceResult
from tekton_core.core.model import StructuralThickness
from tekton_core.design import DesignAssumptions
from tekton_core.design.checks import MPA_TO_KN_M2
from tekton_core.design.plates import check_plate_sample
from tekton_core.design.plates import check_plates
from tekton_core.design.plates import plate_section_properties
from tekton_core.design.plates import worst_per_plate

THICKNESS = 0.2
MODULUS = 1.0 * THICKNESS ** 2 / 6.0
AREA = 1.0 * THICKNESS
F_MD = 0.8 * 24.0 * MPA_TO_KN_M2 / 1.3


def plate_model(grade="C24", thickness=THICKNESS, span_direction=None):
    model = StructuralModel()
    model.materials = {1: Material.resolve(grade)}
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=thickness)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1,
                                        span_direction=span_direction)]
    model.load_cases = [StructuralLoadCase(id=1, name="G", action_category="PERMANENT")]
    return model


def sample(**kwargs):
    return StructuralSurfaceResult(
        surface_id=kwargs.pop("surface_id", 1),
        load_case_id=kwargs.pop("load_case_id", 1),
        position=kwargs.pop("position", Point(0, 0, 0)),
        **kwargs
    )


def check(model=None, **forces):
    model = model or plate_model()
    return check_plate_sample(model, model.surfaces[0], sample(**forces), DesignAssumptions())


def ratio_of(plate_check, name):
    for entry in plate_check.checks:
        if entry.name == name:
            return entry.ratio
    raise AssertionError("no check {!r} in {}".format(name, [c.name for c in plate_check.checks]))


# --- the strip ------------------------------------------------------------

def test_section_properties_are_a_one_metre_strip():
    properties = plate_section_properties(THICKNESS)
    assert properties["area"] == pytest.approx(AREA)
    assert properties["modulus"] == pytest.approx(MODULUS)


def test_a_thicker_plate_has_a_larger_modulus():
    assert plate_section_properties(0.3)["modulus"] > plate_section_properties(0.2)["modulus"]


def test_a_zero_thickness_is_refused():
    with pytest.raises(ValueError, match="must be positive"):
        plate_section_properties(0.0)


# --- bending --------------------------------------------------------------

def test_bending_matches_the_hand_calculation():
    plate_check = check(moment_x=20.0)
    assert ratio_of(plate_check, "bending x") == pytest.approx((20.0 / MODULUS) / F_MD, rel=1e-9)


def test_the_two_directions_are_checked_separately():
    """A plate's x and y are two strips, not two axes of one section - so no
    k_m interaction, and each direction stands on its own."""
    plate_check = check(moment_x=20.0, moment_y=10.0)
    assert ratio_of(plate_check, "bending x") == pytest.approx((20.0 / MODULUS) / F_MD, rel=1e-9)
    assert ratio_of(plate_check, "bending y") == pytest.approx((10.0 / MODULUS) / F_MD, rel=1e-9)
    assert plate_check.governing.name == "bending x"


def test_a_hogging_moment_utilises_like_a_sagging_one():
    assert check(moment_x=-20.0).ratio == pytest.approx(check(moment_x=20.0).ratio)


# --- membrane -------------------------------------------------------------

def test_tension_uses_the_tensile_strength():
    plate_check = check(membrane_force_x=100.0)
    expected = (100.0 / AREA) / (0.8 * 14.0 * MPA_TO_KN_M2 / 1.3)
    assert ratio_of(plate_check, "tension x") == pytest.approx(expected, rel=1e-9)


def test_compression_uses_the_compressive_strength():
    plate_check = check(membrane_force_x=-100.0)
    expected = (100.0 / AREA) / (0.8 * 21.0 * MPA_TO_KN_M2 / 1.3)
    assert ratio_of(plate_check, "compression x") == pytest.approx(expected, rel=1e-9)


def test_bending_plus_tension_is_linear():
    plate_check = check(moment_x=10.0, membrane_force_x=100.0)
    combined = ratio_of(plate_check, "bending + tension x")
    assert combined == pytest.approx(
        ratio_of(plate_check, "tension x") + ratio_of(plate_check, "bending x"), rel=1e-9)


def test_bending_plus_compression_squares_the_membrane_term():
    plate_check = check(moment_x=10.0, membrane_force_x=-100.0)
    combined = ratio_of(plate_check, "bending + compression x")
    assert combined == pytest.approx(
        ratio_of(plate_check, "compression x") ** 2 + ratio_of(plate_check, "bending x"), rel=1e-9)


# --- honesty --------------------------------------------------------------

def test_every_result_carries_the_clt_caveat():
    """Unconservative across the layers - it must never be silent."""
    plate_check = check(moment_x=10.0)
    assert any("CLT" in note for note in plate_check.notes)


def test_span_direction_is_flagged_as_unused():
    from compas.geometry import Vector

    plate_check = check(plate_model(span_direction=Vector(1, 0, 0)), moment_x=10.0)
    assert any("span_direction" in note for note in plate_check.notes)


def test_an_unloaded_sample_yields_no_silent_pass():
    plate_check = check()
    assert plate_check.checks == []
    assert any("no check applicable" in note for note in plate_check.notes)


def test_a_missing_thickness_is_noted_not_crashed():
    model = plate_model()
    model.thicknesses = []
    plate_check = check_plate_sample(model, model.surfaces[0], sample(moment_x=10.0))
    assert plate_check.checks == []
    assert "no thickness" in plate_check.notes[0]


def test_an_assumed_material_is_flagged():
    plate_check = check(plate_model(grade="NotAGrade"), moment_x=10.0)
    assert any("assumed" in note for note in plate_check.notes)


def test_an_overloaded_plate_is_reported_as_failing():
    plate_check = check(moment_x=200.0)
    assert plate_check.ratio > 1.0
    assert not plate_check.passes


def test_the_assumptions_are_carried_through():
    model = plate_model()
    assumptions = DesignAssumptions(service_class=3, load_duration="permanent")
    plate_check = check_plate_sample(model, model.surfaces[0], sample(moment_x=10.0), assumptions)
    assert plate_check.k_mod == pytest.approx(0.5)
    assert plate_check.thickness == pytest.approx(THICKNESS)


# --- the model-wide pass --------------------------------------------------

def model_with_results(*samples):
    model = plate_model()
    result_set = StructuralResultSet(load_case_id=1, name="G")
    result_set.surface_results = {1: list(samples)}
    model.results = {1: result_set}
    return model


def test_check_plates_walks_every_sample_worst_first():
    model = model_with_results(sample(moment_x=5.0), sample(moment_x=30.0), sample(moment_x=1.0))
    checks = check_plates(model, DesignAssumptions())[1]
    assert len(checks) == 3
    assert checks[0].ratio > checks[-1].ratio


def test_worst_per_plate_keeps_one_entry_per_plate():
    """Note the k_mod: check_plates passes the load case, whose category is
    PERMANENT, so k_mod is 0.6 rather than the 0.8 of the bare-sample tests."""
    model = model_with_results(sample(moment_x=5.0), sample(moment_x=30.0))
    worst = worst_per_plate(check_plates(model, DesignAssumptions())[1])
    assert len(worst) == 1
    f_md_permanent = 0.6 * 24.0 * MPA_TO_KN_M2 / 1.3
    assert worst[0].ratio == pytest.approx((30.0 / MODULUS) / f_md_permanent, rel=1e-9)
    assert worst[0].k_mod == pytest.approx(0.6)


def test_a_model_without_plate_results_yields_nothing():
    assert check_plates(plate_model(), DesignAssumptions()) == {}


def test_results_for_a_surface_the_model_does_not_have_are_skipped():
    """The key of surface_results is what identifies the plate, so a result
    set carrying an id the model lost must not be checked against the wrong
    geometry."""
    model = model_with_results(sample(moment_x=10.0))
    model.results[1].surface_results = {99: model.results[1].surface_results[1]}
    assert check_plates(model, DesignAssumptions()) == {}
