"""WP1d: the analysis summary.

The report is a document people act on, so the tests are mostly about what
it must never do: print a zero where a number was not computed, imply a
check that did not run, or call a model balanced without having compared
anything.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "tekton_gh", "src"))

from compas.geometry import Point  # noqa: E402
from compas.geometry import Vector  # noqa: E402

from compas_timber_fea.core.materials import Material  # noqa: E402
from compas_timber_fea.core.model import StructuralLoadCase  # noqa: E402
from compas_timber_fea.core.model import StructuralMember  # noqa: E402
from compas_timber_fea.core.model import StructuralMemberResult  # noqa: E402
from compas_timber_fea.core.model import StructuralModel  # noqa: E402
from compas_timber_fea.core.model import StructuralNode  # noqa: E402
from compas_timber_fea.core.model import StructuralNodeResult  # noqa: E402
from compas_timber_fea.core.model import StructuralPointLoad  # noqa: E402
from compas_timber_fea.core.model import StructuralResultSet  # noqa: E402
from compas_timber_fea.core.model import StructuralSection  # noqa: E402
from compas_timber_fea.core.model import StructuralSupport  # noqa: E402
from compas_timber_fea.design import DesignAssumptions  # noqa: E402
from compas_timber_fea.design.checks import check_model  # noqa: E402
from tekton_gh.summary import applied_load_total  # noqa: E402
from tekton_gh.summary import build_csv  # noqa: E402
from tekton_gh.summary import build_report  # noqa: E402
from tekton_gh.summary import deformation_summary  # noqa: E402
from tekton_gh.summary import force_extremes  # noqa: E402
from tekton_gh.summary import headline_numbers  # noqa: E402
from tekton_gh.summary import reaction_summary  # noqa: E402


def make_model(with_results=True, balanced=True):
    model = StructuralModel()
    model.nodes = [
        StructuralNode(id=1, point=Point(0, 0, 0)),
        StructuralNode(id=2, point=Point(4, 0, 0)),
    ]
    model.sections = [
        StructuralSection(id=1, name="RECT 120/240", material_id=1, width=0.12, height=0.24)
    ]
    model.materials = {1: Material.resolve("C24")}
    model.members = [StructuralMember(id=1, node_start=1, node_end=2, section_id=1)]
    model.supports = [StructuralSupport(id=1, nodes=[1, 2])]
    model.load_cases = [StructuralLoadCase(id=1, name="Imposed", action_category="VARIABLE")]
    model.point_loads = [
        StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -10.0))
    ]
    if not with_results:
        return model

    reaction = Vector(0, 0, 10.0) if balanced else Vector(0, 0, 4.0)
    result_set = StructuralResultSet(load_case_id=1, name="Imposed")
    result_set.node_results = {
        1: StructuralNodeResult(
            node_id=1, load_case_id=1, displacement=Vector(0, 0, 0), reaction_force=reaction
        ),
        2: StructuralNodeResult(node_id=2, load_case_id=1, displacement=Vector(0, 0, -0.012)),
    }
    result_set.member_results = {
        1: [
            StructuralMemberResult(member_id=1, load_case_id=1, position=0.0, axial=-5.0, shear_z=8.0),
            StructuralMemberResult(member_id=1, load_case_id=1, position=0.5, moment_y=15.0),
        ]
    }
    model.results = {1: result_set}
    return model


# --- the pieces ----------------------------------------------------------

def test_deformation_summary_finds_the_worst_node():
    summary = deformation_summary(make_model().results[1])
    assert summary["max"] == pytest.approx(0.012)
    assert summary["max_node"] == 2
    assert summary["count"] == 2


def test_reaction_summary_sums_only_supported_nodes():
    summary = reaction_summary(make_model().results[1])
    assert summary["count"] == 1
    assert summary["fz"] == pytest.approx(10.0)


def test_applied_load_total_flags_a_partial_sum():
    model = make_model()
    assert applied_load_total(model, 1)["fz"] == pytest.approx(-10.0)
    assert applied_load_total(model, 1)["partial"] is False
    model.load_cases[0].self_weight = True
    assert applied_load_total(model, 1)["partial"] is True


def test_force_extremes_records_where_the_extreme_sits():
    extremes = force_extremes(make_model().results[1])
    assert extremes["moment_y"]["value"] == pytest.approx(15.0)
    assert extremes["moment_y"]["position"] == pytest.approx(0.5)
    assert extremes["shear_z"]["value"] == pytest.approx(8.0)


# --- the report ----------------------------------------------------------

def test_report_without_results_says_so():
    report = build_report(make_model(with_results=False))
    assert "nothing was calculated" in report


def test_report_confirms_equilibrium_when_it_balances():
    report = build_report(make_model())
    assert "equilibrium" in report
    assert "OK" in report
    assert "CHECK THE MODEL" not in report


def test_report_flags_a_model_that_does_not_balance():
    report = build_report(make_model(balanced=False))
    assert "CHECK THE MODEL" in report


def test_report_declines_the_check_when_the_load_sum_is_partial():
    model = make_model()
    model.load_cases[0].self_weight = True
    report = build_report(model)
    assert "not checked" in report
    assert "CHECK THE MODEL" not in report


def test_utilisation_absent_is_stated_not_zero():
    report = build_report(make_model())
    assert "Utilisation   not computed" in report
    assert "max        0.000" not in report


def test_report_with_checks_names_the_governing_criterion():
    model = make_model()
    assumptions = DesignAssumptions()
    checks = check_model(model, assumptions)
    report = build_report(model, checks, assumptions)
    assert "Utilisation" in report
    assert "bending" in report
    assert "Design assumptions" in report
    assert "NOT verified" in report
    assert "buckling" in report


def test_report_states_assumptions_it_was_given():
    model = make_model()
    assumptions = DesignAssumptions(service_class=3, load_duration="short-term", gamma_M=1.25)
    report = build_report(model, check_model(model, assumptions), assumptions)
    assert "Service class:      3" in report
    assert "short-term" in report
    assert "1.25" in report


def test_exceeded_members_are_marked():
    model = make_model()
    model.results[1].member_results[1][1].moment_y = 120.0
    assumptions = DesignAssumptions()
    report = build_report(model, check_model(model, assumptions), assumptions)
    assert "EXCEEDED" in report


# --- csv and headline numbers -------------------------------------------

def test_csv_has_a_header_and_one_row_per_sample():
    model = make_model()
    checks = check_model(model, DesignAssumptions())
    rows = build_csv(checks).splitlines()
    assert rows[0].startswith("member_id,load_case,position")
    assert len(rows) == 1 + len(checks[1])
    assert all(row.count(",") == rows[0].count(",") for row in rows)


def test_csv_escapes_a_comma_in_a_field():
    model = make_model()
    model.sections[0].name = "RECT 120/240, planed"
    checks = check_model(model, DesignAssumptions())
    assert '"RECT 120/240, planed"' in build_csv(checks)


def test_headline_numbers_are_none_when_nothing_was_checked():
    numbers = headline_numbers(make_model())
    assert numbers["max_displacement"] == pytest.approx(0.012)
    assert numbers["max_utilization"] is None
    assert numbers["members_over_1"] == 0


def test_headline_numbers_report_the_worst_member():
    model = make_model()
    checks = check_model(model, DesignAssumptions())
    numbers = headline_numbers(model, checks)
    assert numbers["max_utilization"] > 0
    assert numbers["max_utilization_member"] == 1
    assert numbers["governing_check"]


# --- the backend's own ratios (WP1) -------------------------------------------

def make_model_with_backend_ratios():
    model = make_model()
    result_set = model.results[1]
    result_set.member_results[1][0].metadata.update({"utilization": 0.41, "governing_check": "Querkraft 6.1.7"})
    result_set.member_results[1][1].metadata.update({"utilization": 0.83, "governing_check": "Doppelbiegung 6.1.6"})
    result_set.metadata["design"] = {
        "source": "rfem timber design",
        "loadings": ["LK1"],
        "combinations": {"CO1": {"name": "1.5 * LF1", "factors": {1: 1.5}}},
    }
    return model


def test_report_shows_backend_utilisation_with_its_combination():
    model = make_model_with_backend_ratios()
    report = build_report(model)
    assert "Utilisation (rfem timber design, loading LK1)" in report
    assert "0.830  member 1 (Doppelbiegung 6.1.6, t=0.50)" in report
    assert "CO1        1.5 x LC1" in report
    assert "Utilisation   not computed" in report  # our own checks were not run - still said


def test_report_compares_own_checks_with_the_backend():
    model = make_model_with_backend_ratios()
    checks = check_model(model, DesignAssumptions())
    report = build_report(model, checks, DesignAssumptions())
    assert "Utilisation (own EC5 checks)" in report
    assert "vs backend  max deviation" in report


def test_headline_numbers_carry_the_backend_ratio_separately():
    numbers = headline_numbers(make_model_with_backend_ratios())
    assert numbers["max_utilization"] is None
    assert numbers["max_utilization_backend"] == pytest.approx(0.83)
    assert numbers["max_utilization_backend_member"] == 1
