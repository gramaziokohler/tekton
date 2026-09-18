"""WP4: named support types, and authoring more than three of them.

`Display` has always drawn all 64 stiffness combinations; the authoring
could produce three. These tests cover the catalogue that closes that gap,
and the one property that must not regress: a model written before support
types existed still translates to exactly what it translated to before.
"""

import pytest

from compas_timber_fea.core.support_types import DOF_ORDER
from compas_timber_fea.core.support_types import FREE
from compas_timber_fea.core.support_types import INF
from compas_timber_fea.core.support_types import SUPPORT_TYPE_ORDER
from compas_timber_fea.core.support_types import SUPPORT_TYPES
from compas_timber_fea.core.support_types import describe
from compas_timber_fea.core.support_types import key_from_name
from compas_timber_fea.core.support_types import matching_type
from compas_timber_fea.core.support_types import stiffnesses
from compas_timber_fea.core.support_types import support_type_names


# --- the catalogue -------------------------------------------------------

def test_the_classic_three_are_what_they_always_were():
    """Whatever else changes, these three must not move."""
    assert stiffnesses("pinned") == {
        "ux": INF, "uy": INF, "uz": INF, "rx": FREE, "ry": FREE, "rz": FREE}
    assert stiffnesses("fixed") == {dof: INF for dof in DOF_ORDER}
    assert stiffnesses("roller") == {
        "ux": FREE, "uy": FREE, "uz": INF, "rx": FREE, "ry": FREE, "rz": FREE}


def test_a_directional_roller_releases_the_named_direction():
    """RFEM labels a roller by what it frees, and so do we."""
    assert stiffnesses("roller_x")["ux"] == FREE
    assert stiffnesses("roller_x")["uy"] == INF
    assert stiffnesses("roller_y")["uy"] == FREE
    assert stiffnesses("roller_y")["ux"] == INF


def test_sliding_holds_rotation_but_not_horizontal_translation():
    values = stiffnesses("sliding")
    assert values["ux"] == FREE and values["uy"] == FREE
    assert values["uz"] == INF
    assert all(values[dof] == INF for dof in ("rx", "ry", "rz"))


def test_a_hinge_releases_exactly_one_rotation():
    for key, released in (("hinge_x", "rx"), ("hinge_y", "ry"), ("hinge_z", "rz")):
        values = stiffnesses(key)
        assert values[released] == FREE
        assert all(values[dof] == INF for dof in ("rx", "ry", "rz") if dof != released)
        assert all(values[dof] == INF for dof in ("ux", "uy", "uz"))


def test_every_catalogue_entry_is_complete_and_ordered():
    assert set(SUPPORT_TYPE_ORDER) == set(SUPPORT_TYPES)
    for key in SUPPORT_TYPE_ORDER:
        values = stiffnesses(key)
        assert set(values) == set(DOF_ORDER)


def test_drop_down_entries_round_trip():
    names = support_type_names()
    assert len(names) == len(SUPPORT_TYPE_ORDER)
    for entry in names:
        assert key_from_name(entry) in SUPPORT_TYPES


def test_an_unknown_type_is_refused_loudly():
    """A support quietly falling back to pinned changes the structure."""
    with pytest.raises(ValueError, match="Unknown support type"):
        stiffnesses("wobbly")


# --- explicit values and springs ----------------------------------------

def test_six_explicit_values_override_the_type():
    values = stiffnesses("fixed", explicit=[INF, 0, 1000.0, 0, 0, 0])
    assert values["ux"] == INF
    assert values["uz"] == pytest.approx(1000.0)
    assert values["rx"] == FREE


def test_explicit_values_accept_the_words_a_panel_carries():
    values = stiffnesses(None, explicit=["rigid", "free", "inf", "free", "0", "free"])
    assert values["ux"] == INF and values["uz"] == INF
    assert values["uy"] == FREE and values["rx"] == FREE


def test_the_wrong_number_of_explicit_values_is_refused():
    with pytest.raises(ValueError, match="exactly 6"):
        stiffnesses("pinned", explicit=[INF, INF, INF])


def test_unreadable_explicit_value_is_refused():
    with pytest.raises(ValueError, match="Cannot read"):
        stiffnesses(None, explicit=["rigid", "squishy", "free", "free", "free", "free"])


def test_a_spring_overrides_one_degree_of_freedom():
    """A bedded foot: pinned, but vertically on a spring."""
    values = stiffnesses("pinned", springs={"uz": 50000.0})
    assert values["uz"] == pytest.approx(50000.0)
    assert values["ux"] == INF


def test_a_spring_on_an_unknown_dof_is_refused():
    with pytest.raises(ValueError, match="Unknown degree of freedom"):
        stiffnesses("pinned", springs={"uq": 1.0})


# --- reading back --------------------------------------------------------

def test_a_known_set_of_stiffnesses_is_named():
    assert matching_type(stiffnesses("sliding")) == "sliding"
    assert matching_type(stiffnesses("fixed")) == "fixed"


def test_an_unnamed_set_returns_none_rather_than_guessing():
    assert matching_type(stiffnesses("pinned", springs={"uz": 1234.0})) is None


def test_describe_reads_as_a_sentence():
    text = describe(stiffnesses("roller_x"))
    assert "ux free" in text and "uz held" in text
    assert "uz 1" not in text          # held, not a number


def test_describe_shows_a_spring_as_its_value():
    assert "uz 50000" in describe(stiffnesses("pinned", springs={"uz": 50000.0}))


# --- the translator ------------------------------------------------------

def test_points_of_different_types_become_separate_supports():
    from compas_timber.model import TimberModel

    from compas_timber_fea.translator import TimberToStructural

    model = TimberModel.from_json("tests/timber_model_sticks.json")
    beams = list(model.beams)
    for beam, support_type in ((beams[0], "pinned"), (beams[1], "roller_x")):
        point = beam.centerline.start
        beam.attributes["support_points"] = [[point[0], point[1], point[2], support_type]]

    structural = TimberToStructural(source_units="m").translate(model)
    assert len(structural.supports) == 2
    found = {matching_type({dof: getattr(s, dof) for dof in DOF_ORDER}) for s in structural.supports}
    assert found == {"pinned", "roller_x"}


def test_a_point_without_a_type_still_becomes_pinned():
    """Models written before WP4 must translate exactly as they did."""
    from compas_timber.model import TimberModel

    from compas_timber_fea.translator import TimberToStructural

    model = TimberModel.from_json("tests/timber_model_sticks.json")
    beam = list(model.beams)[0]
    point = beam.centerline.start
    beam.attributes["support_points"] = [[point[0], point[1], point[2]]]

    structural = TimberToStructural(source_units="m").translate(model)
    assert len(structural.supports) == 1
    values = {dof: getattr(structural.supports[0], dof) for dof in DOF_ORDER}
    assert matching_type(values) == "pinned"
