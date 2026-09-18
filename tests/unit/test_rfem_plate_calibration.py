"""WP0b-Rest: the calibration plate, RFEM against the closed form and against OpenSees.

``plate_rfem_calibration.json`` is RFEM 6.13's answer for the simply
supported square plate of ``test_opensees_shells`` (recorded with
``tests/record_plate_rfem.py`` on 2026-09-19). Two things are pinned:

1. RFEM itself sits where a Mindlin plate with g = 10 should sit relative
   to the Kirchhoff/Navier value - so the recorded numbers are trustworthy;
2. the OpenSees adapter reproduces them, membrane forces and moments
   included (skipped where openseespy cannot load).

What the recording found, and what the fixture therefore encodes: RFEM's
library variant of C24 for surfaces is orthotropic with E90 across, which
turned the plate into a one-way slab 3.2x softer than Navier. The importer
now overwrites that variant with the neutral (isotropic) stiffness -
``MemberMapper.plate_material_values`` - and this fixture is the proof.
"""

import json
import os

import pytest

from compas_timber_fea.core.model import StructuralModel

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NEUTRAL_GRAVITY = 9.81
SIDE = 4.0
THICKNESS = 0.2
NAVIER_DEFLECTION = 0.00406      # w = c q a^4 / D, simply supported square plate
NAVIER_MOMENT = 0.0368           # m = c q a^2 at the centre, nu = 0


@pytest.fixture(scope="module")
def recorded():
    with open(os.path.join(FIXTURES, "plate_rfem_calibration.json")) as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def model():
    return StructuralModel.from_json(os.path.join(FIXTURES, "plate_structural.json"))


def closed_form(model, gravity):
    material = model.materials[1]
    E = material.E0_mean * 1000.0                                  # MPa -> kN/m2
    D = E * THICKNESS ** 3 / (12 * (1 - material.poisson ** 2))
    q = material.density_mean * gravity / 1000.0 * THICKNESS       # kN/m2
    return NAVIER_DEFLECTION * q * SIDE ** 4 / D, NAVIER_MOMENT * q * SIDE ** 2, q


# --- RFEM against the closed form ---------------------------------------------

def test_rfem_carries_the_whole_self_weight(recorded, model):
    _, _, q = closed_form(model, recorded["gravity"])
    assert recorded["reaction_sum_z"] == pytest.approx(q * SIDE * SIDE, rel=1e-3)


def test_rfem_deflection_is_navier_plus_shear(recorded, model):
    """Mindlin at t/a = 0.05 sits a few percent above Kirchhoff; 3.2x would be the one-way slab."""
    expected, _, _ = closed_form(model, recorded["gravity"])
    ratio = abs(recorded["max_displacement"]["uz"]) / expected
    assert 1.0 < ratio < 1.05, ratio
    x, y, _ = recorded["max_displacement"]["position"]
    assert abs(x - SIDE / 2) < 0.4 and abs(y - SIDE / 2) < 0.4


def test_rfem_plate_is_isotropic(recorded, model):
    """m_x == m_y at the centre: the orthotropic library variant gave 1.59 vs 0.03."""
    _, expected, _ = closed_form(model, recorded["gravity"])
    centre = recorded["max_displacement"]
    assert centre["m_x"] == pytest.approx(centre["m_y"], rel=1e-6)
    assert centre["m_x"] == pytest.approx(expected, rel=0.03)
    assert all(abs(s["n_x"]) < 1e-6 and abs(s["n_y"]) < 1e-6 for s in recorded["samples"]), "a flat plate under gravity has no membrane forces"


# --- OpenSees against RFEM ------------------------------------------------------

@pytest.fixture(scope="module")
def opensees_results(model):
    from compas_opensees import run_model
    from compas_opensees.runner import load_opensees

    try:
        load_opensees()
    except Exception as exc:  # no solver on this machine - the RFEM half still ran
        pytest.skip("openseespy not usable here: {}".format(exc))

    run_model(model)
    return model.results[1]


def test_opensees_matches_rfem_deflection(recorded, opensees_results):
    scale = recorded["gravity"] / NEUTRAL_GRAVITY
    ours = max(abs(s.displacement.z) for s in opensees_results.surface_results[1]) * scale
    assert ours == pytest.approx(abs(recorded["max_displacement"]["uz"]), rel=0.06)


def test_opensees_matches_rfem_centre_moment(recorded, opensees_results):
    scale = recorded["gravity"] / NEUTRAL_GRAVITY
    centre = max(opensees_results.surface_results[1], key=lambda s: abs(s.displacement.z))
    assert centre.moment_x * scale == pytest.approx(recorded["max_displacement"]["m_x"], rel=0.10)
    assert centre.moment_y * scale == pytest.approx(recorded["max_displacement"]["m_y"], rel=0.10)


def test_opensees_matches_rfem_reactions(recorded, opensees_results):
    scale = recorded["gravity"] / NEUTRAL_GRAVITY
    ours = sum(n.reaction_force.z for n in opensees_results.node_results.values() if n.reaction_force) * scale
    assert ours == pytest.approx(recorded["reaction_sum_z"], rel=1e-3)
