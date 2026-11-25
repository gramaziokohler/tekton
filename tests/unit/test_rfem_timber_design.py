"""WP1: RFEM's timber design ratios, parsed offline and cross-checked against WP1b.

The fixture is the raw ratio table RFEM 6.13 produced for the sticks model
on 2026-09-18 (see its ``note`` and ``design_setup``), plus the CO1 section
forces for a subset of members. Two things are pinned here:

1. the parser turns the table into ``metadata["utilization"]`` on the
   member results, on the same stations as the forces;
2. our own EC5 checks (``tekton_core.design``), fed RFEM's CO1 forces
   and RFEM's assumptions, reproduce RFEM's ratio per member.

The second is the reason WP1b exists as a *test* and not just a feature:
the two paths are independent, so agreement is evidence and disagreement is
a bug on one side. The one known difference is the size factor k_h, which
RFEM leaves off by default - hence ``DesignAssumptions.size_factor=False``.
"""

import json
import os

import pandas as pd
import pytest

from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralResultSet
from tekton_core.design import DesignAssumptions
from tekton_core.design import check_model
from tekton_core.design.checks import worst_per_member

from tekton_dlubal.dlubal.result_parsing import design_ratio_summary
from tekton_dlubal.dlubal.result_parsing import member_lengths_from_model
from tekton_dlubal.dlubal.result_parsing import parse_member_design_ratios
from tekton_dlubal.dlubal.result_parsing import parse_member_internal_forces

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="module")
def recorded():
    with open(os.path.join(FIXTURES, "sticks_rfem_timber_design.json")) as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def model():
    return StructuralModel.from_json(os.path.join(FIXTURES, "sticks_structural.json"))


def frame(table):
    return pd.DataFrame(table["rows"], columns=table["columns"])


# --- parsing --------------------------------------------------------------

def test_ratios_land_on_the_force_stations(recorded, model):
    lengths = member_lengths_from_model(model)
    forces = parse_member_internal_forces(frame(recorded["co1_forces"]), 1, lengths)
    stations_before = {m: [r.position for r in rows] for m, rows in forces.items()}

    merged = parse_member_design_ratios(frame(recorded["ratios"]), 1, lengths, forces)

    # No new stations for members that had forces: RFEM designs where it reports forces.
    for member_id, positions in stations_before.items():
        assert [r.position for r in merged[member_id]] == positions

    # The worst member of the model, at its worst station.
    worst = max((r for rows in merged.values() for r in rows), key=lambda r: r.metadata.get("utilization", 0.0))
    assert worst.member_id == 27
    assert worst.metadata["utilization"] == pytest.approx(0.29895, abs=1e-4)
    assert "6.2.4" in worst.metadata["governing_check"]
    assert worst.metadata["check_type"] == "SP6300.00"
    assert worst.metadata["design_loading"] == "LK1"


def test_ratios_stand_alone_without_forces(recorded, model):
    merged = parse_member_design_ratios(frame(recorded["ratios"]), 1, member_lengths_from_model(model))
    assert len(merged) == 304  # the timber members; the 100 couplings carry no section
    assert all(0.0 <= r.position <= 1.0 for rows in merged.values() for r in rows)
    assert all("utilization" in r.metadata for rows in merged.values() for r in rows)


def test_summary_names_the_design_loadings(recorded):
    summary = design_ratio_summary(frame(recorded["ratios"]))
    assert summary == {"loadings": ["LK1"], "design_situations": [1]}


# --- cross-check against WP1b -------------------------------------------------

def test_own_checks_reproduce_rfem_ratios(recorded, model):
    """Per member, our governing ratio equals RFEM's to within 0.2 %."""
    lengths = member_lengths_from_model(model)
    model.results = {
        1: StructuralResultSet(
            load_case_id=1, name="CO1",
            member_results=parse_member_internal_forces(frame(recorded["co1_forces"]), 1, lengths),
        )
    }
    assumptions = DesignAssumptions(service_class=1, load_duration="permanent", size_factor=False)
    ours = {check.member_id: check for check in worst_per_member(check_model(model, assumptions)[1])}

    ratios = frame(recorded["ratios"])
    rfem = ratios.groupby("member_no")["design_ratio"].max()

    compared = 0
    for member_id in recorded["members_subset"]:
        expected = float(rfem[member_id])
        if expected < 0.01:
            # RFEM reports "negligible internal forces" as ratio 0 - nothing to compare.
            continue
        assert ours[member_id].ratio == pytest.approx(expected, rel=2e-3), member_id
        assert ours[member_id].k_mod == pytest.approx(0.6)
        assert ours[member_id].gamma_M == pytest.approx(1.3)
        compared += 1
    assert compared >= 20


def test_size_factor_is_the_known_difference(recorded, model):
    """With k_h on, our bending ratios sit 7.8 % below RFEM's (h = 100 mm)."""
    lengths = member_lengths_from_model(model)
    model.results = {
        1: StructuralResultSet(
            load_case_id=1, name="CO1",
            member_results=parse_member_internal_forces(frame(recorded["co1_forces"]), 1, lengths),
        )
    }
    assumptions = DesignAssumptions(service_class=1, load_duration="permanent", size_factor=True)
    ours = {check.member_id: check for check in worst_per_member(check_model(model, assumptions)[1])}
    rfem = frame(recorded["ratios"]).groupby("member_no")["design_ratio"].max()

    k_h = (0.150 / 0.10) ** 0.2
    assert ours[27].ratio * k_h == pytest.approx(float(rfem[27]), rel=2e-3)
