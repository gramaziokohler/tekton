"""WP3: EN 1990 action categories and the combinations they generate.

The reference values are hand-written from EN 1990 Table A1.1 and A1.2(B),
and the combinations are spelled out in the tests so a reader can check them
against the code without running anything. A combination generator that is
subtly wrong produces plausible numbers everywhere downstream, so the
arithmetic is asserted term by term rather than by shape.
"""

import pytest

from compas_timber_fea.core.load_catalogue import CATEGORIES
from compas_timber_fea.core.load_catalogue import CATEGORY_ORDER
from compas_timber_fea.core.load_catalogue import GAMMA_G_FAVOURABLE
from compas_timber_fea.core.load_catalogue import GAMMA_G_UNFAVOURABLE
from compas_timber_fea.core.load_catalogue import GAMMA_Q_UNFAVOURABLE
from compas_timber_fea.core.load_catalogue import category
from compas_timber_fea.core.load_catalogue import category_names
from compas_timber_fea.core.load_catalogue import describe
from compas_timber_fea.core.load_catalogue import generate_combinations
from compas_timber_fea.core.load_catalogue import key_from_name
from compas_timber_fea.core.load_catalogue import to_load_combinations
from compas_timber_fea.core.model import StructuralLoadCase


def cases(*specs):
    return [StructuralLoadCase(id=i, name=name, action_category=cat,
                               self_weight=(cat == "PERMANENT"))
            for i, (name, cat) in enumerate(specs, start=1)]


def only(combinations, kind):
    return [c for c in combinations if c.combination_type == kind]


# --- the catalogue -------------------------------------------------------

def test_psi_factors_match_en_1990_table_a11():
    assert (CATEGORIES["A"].psi_0, CATEGORIES["A"].psi_1, CATEGORIES["A"].psi_2) == (0.7, 0.5, 0.3)
    assert (CATEGORIES["E"].psi_0, CATEGORIES["E"].psi_1, CATEGORIES["E"].psi_2) == (1.0, 0.9, 0.8)
    assert (CATEGORIES["H"].psi_0, CATEGORIES["H"].psi_1, CATEGORIES["H"].psi_2) == (0.0, 0.0, 0.0)
    assert (CATEGORIES["SNOW"].psi_0, CATEGORIES["SNOW"].psi_2) == (0.5, 0.0)
    assert (CATEGORIES["WIND"].psi_0, CATEGORIES["WIND"].psi_2) == (0.6, 0.0)


def test_partial_factors_follow_the_action_kind():
    assert CATEGORIES["PERMANENT"].gamma_unfavourable == pytest.approx(GAMMA_G_UNFAVOURABLE)
    assert CATEGORIES["PERMANENT"].gamma_favourable == pytest.approx(GAMMA_G_FAVOURABLE)
    assert CATEGORIES["A"].gamma_unfavourable == pytest.approx(GAMMA_Q_UNFAVOURABLE)


def test_categories_carry_a_duration_class_for_k_mod():
    """The design checks need it; without it they guess from the name."""
    assert CATEGORIES["PERMANENT"].load_duration == "permanent"
    assert CATEGORIES["E"].load_duration == "long-term"       # storage
    assert CATEGORIES["SNOW"].load_duration == "short-term"
    assert CATEGORIES["WIND"].load_duration == "instantaneous"


def test_lookup_tolerates_case_and_whitespace():
    assert category("a").key == "A"
    assert category("  snow ").key == "SNOW"
    assert category(CATEGORIES["B"]).key == "B"


def test_an_unknown_category_falls_back_and_says_so():
    found = category("CATEGORY_Z")
    assert found.key == "VARIABLE"
    assert "borrowed" in found.note.lower()


def test_the_legacy_variable_category_still_resolves():
    """Models written before the catalogue carry action_category='VARIABLE'."""
    assert category("VARIABLE").psi_0 == pytest.approx(0.7)


def test_drop_down_entries_round_trip():
    names = category_names()
    assert len(names) == len(CATEGORY_ORDER)
    for entry in names:
        assert key_from_name(entry) in CATEGORIES


# --- ULS -----------------------------------------------------------------

def test_every_variable_action_leads_once():
    combinations = only(generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Snow", "SNOW"))), "ULS")
    assert len(combinations) == 2
    assert {c.leading_case for c in combinations} == {2, 3}


def test_imposed_leading_matches_the_hand_calculation():
    """1.35 G + 1.50 Q_A + 1.50 * 0.5 Snow."""
    combination = next(c for c in generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Snow", "SNOW"))) if c.leading_case == 2)
    assert combination.factors[1] == pytest.approx(1.35)
    assert combination.factors[2] == pytest.approx(1.50)
    assert combination.factors[3] == pytest.approx(0.75)


def test_snow_leading_matches_the_hand_calculation():
    """1.35 G + 1.50 Snow + 1.50 * 0.7 Q_A."""
    combination = next(c for c in generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Snow", "SNOW"))) if c.leading_case == 3)
    assert combination.factors[1] == pytest.approx(1.35)
    assert combination.factors[2] == pytest.approx(1.05)
    assert combination.factors[3] == pytest.approx(1.50)


def test_a_category_with_psi_zero_is_left_out_when_not_leading():
    """Roofs (H) have psi_0 = 0: they contribute nothing unless they lead."""
    combination = next(c for c in generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Roof", "H"))) if c.leading_case == 2)
    assert 3 not in combination.factors


def test_permanent_only_still_yields_a_design_situation():
    combinations = only(generate_combinations(cases(("G", "PERMANENT"))), "ULS")
    assert len(combinations) == 1
    assert combinations[0].factors == {1: pytest.approx(1.35)}


def test_favourable_permanent_uses_gamma_one():
    """For uplift, self-weight helps and must not be inflated."""
    combination = only(generate_combinations(
        cases(("G", "PERMANENT"), ("Wind", "WIND")), favourable_permanent=True), "ULS")[0]
    assert combination.factors[1] == pytest.approx(1.00)
    assert combination.factors[2] == pytest.approx(1.50)


def test_no_load_cases_yields_nothing():
    assert generate_combinations([]) == []


# --- SLS -----------------------------------------------------------------

def test_characteristic_combination_is_unfactored():
    combination = next(c for c in generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Snow", "SNOW")))
        if c.combination_type == "SLS_CHARACTERISTIC" and c.leading_case == 2)
    assert combination.factors[1] == pytest.approx(1.0)
    assert combination.factors[2] == pytest.approx(1.0)
    assert combination.factors[3] == pytest.approx(0.5)      # psi_0 snow


def test_quasi_permanent_uses_psi_2_and_drops_what_it_zeroes():
    combination = next(c for c in generate_combinations(cases(
        ("G", "PERMANENT"), ("Imposed", "A"), ("Snow", "SNOW")))
        if c.combination_type == "SLS_QUASI_PERMANENT")
    assert combination.factors[1] == pytest.approx(1.0)
    assert combination.factors[2] == pytest.approx(0.3)      # psi_2 cat A
    assert 3 not in combination.factors                      # psi_2 snow = 0


def test_sls_can_be_switched_off():
    combinations = generate_combinations(
        cases(("G", "PERMANENT"), ("Imposed", "A")), include_sls=False)
    assert {c.combination_type for c in combinations} == {"ULS"}


# --- conversion and reporting -------------------------------------------

def test_conversion_to_load_combination_objects():
    generated = generate_combinations(cases(("G", "PERMANENT"), ("Imposed", "A")))
    combinations = to_load_combinations(generated, start_id=10)
    assert [c.id for c in combinations] == list(range(10, 10 + len(generated)))
    assert combinations[0].name == generated[0].name
    assert combinations[0].factors == generated[0].factors


def test_description_names_the_clause_and_the_terms():
    lines = describe(generate_combinations(cases(("G", "PERMANENT"), ("Imposed", "A"))))
    assert any("6.10" in line for line in lines)
    assert any("1.35x LC1" in line for line in lines)


def test_every_combination_records_the_expression_it_came_from():
    for combination in generate_combinations(cases(("G", "PERMANENT"), ("Imposed", "A"))):
        assert combination.expression.startswith("EN 1990")
