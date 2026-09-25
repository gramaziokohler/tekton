"""The OpenSees backend, end to end, offline.

Three layers of evidence:

1. Closed-form: a simply supported beam and a cantilever with a spring
   release, checked to the printed digits - the same checks as the spike,
   now guarding the adapter.
2. Cross-backend: the sticks model against RFEM numbers recorded in
   ``fixtures/sticks_rfem_calibration.json``. Signs must agree; magnitudes
   within what RFEM's g = 10 and its shear deformation account for.
3. The chain: results attach to the timber model - the first test in this
   suite that exercises ``attach_results_to_timber`` on real solver output.

openseespy is a conditional dependency (Windows wheel needs Python 3.12);
the whole module is skipped without it.
"""

import json
import os

import pytest
from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralPointLoad
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.releases import MemberRelease

pytest.importorskip("openseespy", reason="openseespy not installed (needs Python >= 3.12 on Windows)")

from compas_opensees import run_model  # noqa: E402
from compas_opensees.conventions import G_ACC  # noqa: E402
from compas_opensees.conventions import local_axes  # noqa: E402
from compas_opensees.conventions import rectangle_torsion_constant  # noqa: E402
from compas_opensees.conventions import section_constants  # noqa: E402
from compas_opensees.conventions import to_local  # noqa: E402
from compas_opensees.runner import load_opensees  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

E_C24 = 11000.0  # MPa
B, H = 0.12, 0.24


def beam_model(length=4.0, supports=("fork", "roller"), release_end=None):
    """One C24 120x240 member along X, section width along Y.

    A simply supported beam in 3D needs its torsion held somewhere - two
    supports that both free rx let the beam spin about its own axis, and
    OpenSees rightly refuses to solve that. Hence a fork at one end.
    """
    model = StructuralModel()
    model.nodes = [StructuralNode(id=1, point=Point(0, 0, 0)), StructuralNode(id=2, point=Point(length, 0, 0))]
    model.materials = {1: "C24"}
    model.sections = [StructuralSection(id=1, name="R", material_id=1, width=B, height=H)]
    model.members = [StructuralMember(id=1, node_start=1, node_end=2, section_id=1, orientation_vector=Vector(0, 1, 0), release_end=release_end)]
    kinds = {
        "pinned": dict(rx=0.0, ry=0.0, rz=0.0),
        "fork": dict(ry=0.0, rz=0.0),
        "roller": dict(ux=0.0, rx=0.0, ry=0.0, rz=0.0),
        "fixed": dict(),
        None: None,
    }
    model.supports = [StructuralSupport(id=i + 1, nodes=[i + 1], **kinds[k]) for i, k in enumerate(supports) if kinds[k] is not None]
    model.load_cases = [StructuralLoadCase(id=1, name="test", action_category="PERMANENT", self_weight=False)]
    return model


# ------------------------------------------------------------------ conventions


def test_section_constants_and_torsion():
    area, iy, iz, j = section_constants(0.12, 0.24)
    assert area == pytest.approx(0.0288)
    assert iy == pytest.approx(0.12 * 0.24 ** 3 / 12)
    assert iz == pytest.approx(0.24 * 0.12 ** 3 / 12)
    assert j == pytest.approx(0.229 * 0.12 ** 3 * 0.24)  # h/b = 2 -> beta 0.229
    assert rectangle_torsion_constant(0.24, 0.12) == j  # order does not matter
    assert rectangle_torsion_constant(0.1, 0.1) == pytest.approx(0.141 * 0.1 ** 4)


def test_local_axes_and_projection():
    x, y, z = local_axes(Point(0, 0, 0), Point(0, 0, 3), Vector(0, 1, 0))  # a column
    assert list(x) == [0, 0, 1] and list(y) == [0, 1, 0]
    assert [round(c, 9) for c in z] == [-1, 0, 0]
    # a global -z force on a column is axial
    assert [round(c, 9) for c in to_local((0, 0, -5), (x, y, z))] == [-5, 0, 0]
    # degenerate orientation falls back to a valid frame
    x, y, z = local_axes(Point(0, 0, 0), Point(0, 0, 3), Vector(0, 0, 1))
    assert abs(y.dot(x)) < 1e-9 and abs(z.dot(x)) < 1e-9


# ----------------------------------------------------------------- closed form


def test_simply_supported_beam_under_uniform_load():
    q, L = 5.0, 4.0
    model = beam_model(L)
    model.member_loads = [StructuralMemberLoad(id=1, member_id=1, load_case_id=1, force=Vector(0, 0, -q))]

    run_model(model)

    rs = model.results[1]
    e = E_C24 * 1000.0
    iy = B * H ** 3 / 12
    # ends: reactions on the structure point up
    assert rs.node_results[1].reaction_force.z == pytest.approx(q * L / 2, rel=1e-6)
    assert rs.node_results[2].reaction_force.z == pytest.approx(q * L / 2, rel=1e-6)
    # midspan moment magnitude qL²/8 at the middle Lobatto station (9 stations -> index 4)
    rows = rs.member_results[1]
    mid = rows[len(rows) // 2]
    assert mid.position == pytest.approx(0.5)
    assert abs(mid.moment_y) == pytest.approx(q * L ** 2 / 8, rel=1e-6)
    assert rows[0].moment_y == pytest.approx(0.0, abs=1e-9)
    # shear: qL/2 at the ends, zero at midspan, sign flips
    assert abs(rows[0].shear_z) == pytest.approx(q * L / 2, rel=1e-6)
    assert mid.shear_z == pytest.approx(0.0, abs=1e-9)
    assert rows[0].shear_z * rows[-1].shear_z < 0
    # deflection: OpenSees reports the node, not the midspan - check the end rotations instead
    theta = q * L ** 3 / (24 * e * iy)
    assert abs(rs.node_results[1].rotation.y) == pytest.approx(theta, rel=1e-6)


def test_cantilever_with_rotational_spring_release():
    """A spring release at the fixed end: tip deflection PL³/3EI + PL²/k, exact."""
    P, L, k = 10.0, 4.0, 2000.0
    model = beam_model(L, supports=("fixed", None))
    model.members[0].release_start = MemberRelease(ry=k, name="spring")
    model.point_loads = [StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -P))]

    run_model(model)

    e = E_C24 * 1000.0
    iy = B * H ** 3 / 12
    tip = model.results[1].node_results[2].displacement.z
    assert tip == pytest.approx(-(P * L ** 3 / (3 * e * iy) + P * L * L / k), rel=1e-5)
    assert model.results[1].node_results[1].reaction_force.z == pytest.approx(P, rel=1e-6)


def test_self_weight_is_rho_a_g():
    L = 4.0
    model = beam_model(L)
    model.load_cases[0].self_weight = True

    run_model(model)

    w = 420.0 * G_ACC / 1000.0 * B * H  # kN/m
    total = sum(model.results[1].node_results[n].reaction_force.z for n in (1, 2))
    assert total == pytest.approx(w * L, rel=1e-6)


def test_mechanism_fails_loudly():
    """Both supports free the torsion: the beam can spin about its axis. analyze != 0 -> a named exception, not zeros."""
    model = beam_model(4.0, supports=("pinned", "roller"))
    model.point_loads = [StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -1.0))]

    with pytest.raises(RuntimeError, match="failed to solve"):
        run_model(model)


def test_a_degenerate_surface_is_reported_not_silently_dropped():
    """Surfaces are built since WP0b (see test_opensees_shells.py); an outline
    that is not a polygon still has to say so rather than vanish."""
    from compas_timber_fea.core.model import StructuralSurface

    from compas_timber_fea.core.model import StructuralThickness

    model = beam_model(4.0)
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=0.1)]
    model.surfaces = [StructuralSurface(id=1, nodes=[1, 2, 2, 1], thickness_id=1)]

    result = run_model(model)
    assert any("fewer than 3" in line for line in result.log)


# ---------------------------------------------------------------- cross-backend


@pytest.fixture(scope="module")
def sticks():
    model = StructuralModel.from_json(os.path.join(FIXTURES, "sticks_structural.json"))
    run_model(model)
    with open(os.path.join(FIXTURES, "sticks_rfem_calibration.json")) as handle:
        return model, json.load(handle)


def test_sticks_solves_fast_and_completely(sticks):
    model, _ = sticks
    rs = model.results[1]
    assert len(rs.member_results) == 404
    assert len(rs.node_results) == 344
    assert sum(1 for n in rs.node_results.values() if n.reaction_force) == 4


def test_sticks_matches_rfem_within_gravity_and_shear(sticks):
    """RFEM runs g = 10 and Timoshenko beams; OpenSees g = 9.81 and Euler-Bernoulli. ~2 % + a few %."""
    model, rfem = sticks
    rs = model.results[1]
    g_ratio = G_ACC / rfem["gravity"]
    total = sum(n.reaction_force.z for n in rs.node_results.values() if n.reaction_force)
    assert total == pytest.approx(sum(v[2] for v in rfem["reactions"].values()) * g_ratio, rel=1e-3)
    for nid, reaction in rfem["reactions"].items():
        ours = rs.node_results[int(nid)].reaction_force
        assert ours.z > 0 and reaction[2] > 0, "reactions must be the force on the structure in both backends"
        assert ours.z == pytest.approx(reaction[2] * g_ratio, rel=2e-2)
    ours = max(n.displacement.length for n in rs.node_results.values())
    assert ours == pytest.approx(rfem["max_displacement"] * g_ratio, rel=0.12)


def test_sticks_signs_agree_with_rfem_station_by_station(sticks):
    model, rfem = sticks
    rs = model.results[1]
    kinds = {m.id: m.member_type for m in model.members}
    compared = 0
    for mid, stations in rfem["members"].items():
        if kinds[int(mid)] != "BEAM":
            continue
        ours = {round(r.position, 3): r for r in rs.member_results[int(mid)]}
        for station in stations:
            row = ours.get(round(station["t"], 3))
            if row is None:
                continue
            for key, attr in (("N", "axial"), ("My", "moment_y"), ("Mz", "moment_z"), ("Vz", "shear_z"), ("Vy", "shear_y")):
                theirs, mine = station[key], getattr(row, attr)
                if abs(theirs) < 0.01 or abs(mine) < 0.01:
                    continue
                assert theirs * mine > 0, "{} {} at t={}: RFEM {} vs OpenSees {}".format(mid, key, station["t"], theirs, mine)
                assert mine == pytest.approx(theirs * G_ACC / rfem["gravity"], rel=0.15)
                compared += 1
    assert compared > 40


# ---------------------------------------------------------------------- the chain


def test_results_attach_to_the_timber_model(sticks):
    from compas.data import json_load
    from compas_timber_fea.results import attach_results_to_timber

    model, _ = sticks
    timber = json_load(os.path.join(os.path.dirname(__file__), "..", "timber_model_sticks.json"))
    attached = attach_results_to_timber(model, timber)

    assert len(attached) == 84
    beam = next(iter(timber.beams))
    case = beam.attributes["analysis"]["load_cases"][1]
    assert len(case["samples"]) >= 9
    assert "My" in case["envelope"]


def test_opensees_loads_on_this_platform():
    ops = load_opensees()
    assert ops.version()


def test_station_displacements_follow_the_bending_line():
    """Hermite interpolation from the end rotations: midspan sag of the simply supported beam within 1 %."""
    q, L = 5.0, 4.0
    model = beam_model(L)
    model.member_loads = [StructuralMemberLoad(id=1, member_id=1, load_case_id=1, force=Vector(0, 0, -q))]

    run_model(model)

    rows = model.results[1].member_results[1]
    mid = rows[len(rows) // 2]
    e = E_C24 * 1000.0
    iy = B * H ** 3 / 12
    assert mid.displacement.z == pytest.approx(-5 * q * L ** 4 / (384 * e * iy), rel=0.01)
    assert rows[0].displacement.length == pytest.approx(0.0, abs=1e-9)


def test_lateral_bending_line_has_the_right_sign_too():
    """A uniform load along local y (global Y here): the midspan sag must follow the load direction."""
    q, L = 2.0, 4.0
    model = beam_model(L)
    model.member_loads = [StructuralMemberLoad(id=1, member_id=1, load_case_id=1, force=Vector(0, -q, 0))]

    run_model(model)

    rows = model.results[1].member_results[1]
    mid = rows[len(rows) // 2]
    e = E_C24 * 1000.0
    iz = H * B ** 3 / 12
    assert mid.displacement.y == pytest.approx(-5 * q * L ** 4 / (384 * e * iz), rel=0.01)


def test_fully_fixed_model_is_refused_before_lapack_aborts():
    model = beam_model(4.0, supports=("fixed", "fixed"))
    model.point_loads = [StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -1.0))]

    with pytest.raises(ValueError, match="Nothing to solve"):
        run_model(model)
