"""WP1b: the EC5 checks computed in the neutral layer.

The reference numbers are hand calculations, written out in the test so a
reader can follow them without running anything. A C24 rectangle 120/240 in
service class 1, medium-term duration:

    A     = 0.12 * 0.24            = 0.0288 m2
    W_y   = 0.12 * 0.24^2 / 6      = 0.001152 m3
    f_md  = k_mod * f_mk / gamma_M = 0.8 * 24 / 1.3   = 14.769 MPa
    f_vd  = 0.8 * 4.0 / 1.3                           =  2.462 MPa
"""

import math

import pytest

from tekton_core.core.materials import Material
from tekton_core.design import DesignAssumptions
from tekton_core.design import gamma_M_for
from tekton_core.design import k_h_bending
from tekton_core.design import k_mod
from tekton_core.design import member_length
from tekton_core.design import section_properties
from tekton_core.design.checks import MPA_TO_KN_M2
from tekton_core.design.checks import check_member
from tekton_core.design.checks import worst_per_member


class FakeSection:
    def __init__(self, width=0.12, height=0.24, shape_type="rectangular", material_id=1):
        self.id = 1
        self.name = "RECT 120/240"
        self.material_id = material_id
        self.width = width
        self.height = height
        self.shape_type = shape_type


class FakeMember:
    def __init__(self, member_id=1, member_type="BEAM"):
        self.id = member_id
        self.node_start = 1
        self.node_end = 2
        self.section_id = 1
        self.member_type = member_type


class FakeResult:
    def __init__(self, **kwargs):
        self.member_id = kwargs.pop("member_id", 1)
        self.load_case_id = kwargs.pop("load_case_id", 1)
        self.position = kwargs.pop("position", 0.5)
        self.axial = kwargs.pop("axial", 0.0)
        self.shear_y = kwargs.pop("shear_y", 0.0)
        self.shear_z = kwargs.pop("shear_z", 0.0)
        self.torsion = kwargs.pop("torsion", 0.0)
        self.moment_y = kwargs.pop("moment_y", 0.0)
        self.moment_z = kwargs.pop("moment_z", 0.0)
        assert not kwargs, kwargs


class FakeNode:
    def __init__(self, node_id, point):
        self.id = node_id
        self.point = point


class FakeModel:
    def __init__(self, section=None, grade="C24", nodes=None):
        self.sections = [section or FakeSection()]
        self.materials = {1: Material.resolve(grade)}
        self.members = [FakeMember()]
        self.nodes = nodes or []
        self.load_cases = []
        self.results = {}


def check(**forces):
    model = FakeModel()
    return check_member(model, model.members[0], FakeResult(**forces), DesignAssumptions())


def ratio_of(member_check, name):
    for entry in member_check.checks:
        if entry.name == name:
            return entry.ratio
    raise AssertionError("no check named {!r} in {}".format(name, [c.name for c in member_check.checks]))


# --- section geometry ----------------------------------------------------

def test_rectangular_section_properties():
    properties = section_properties(FakeSection())
    assert properties["area"] == pytest.approx(0.0288)
    assert properties["W_y"] == pytest.approx(0.001152)
    assert properties["W_z"] == pytest.approx(0.000576)
    assert properties["I_y"] == pytest.approx(0.12 * 0.24 ** 3 / 12.0)
    assert properties["shear_factor"] == pytest.approx(1.5)
    assert properties["is_approximated"] is False


def test_circular_section_properties():
    properties = section_properties(FakeSection(width=0.2, height=0.2, shape_type="circular"))
    assert properties["area"] == pytest.approx(math.pi * 0.01)
    assert properties["W_y"] == pytest.approx(math.pi * 0.2 ** 3 / 32.0)
    assert properties["shear_factor"] == pytest.approx(4.0 / 3.0)


def test_unknown_shape_is_approximated_and_says_so():
    properties = section_properties(FakeSection(shape_type="i-beam"))
    assert properties["is_approximated"] is True
    assert properties["area"] == pytest.approx(0.0288)


def test_section_without_dimensions_raises():
    with pytest.raises(ValueError):
        section_properties(FakeSection(width=0.0))


def test_member_length_and_missing_node():
    nodes = [FakeNode(1, (0.0, 0.0, 0.0)), FakeNode(2, (3.0, 4.0, 0.0))]
    model = FakeModel(nodes=nodes)
    assert member_length(model, model.members[0]) == pytest.approx(5.0)
    assert member_length(FakeModel(), FakeMember()) == 0.0


# --- factors -------------------------------------------------------------

def test_k_mod_table():
    assert k_mod(1, "medium-term") == pytest.approx(0.8)
    assert k_mod(1, "permanent") == pytest.approx(0.6)
    assert k_mod(3, "instantaneous") == pytest.approx(0.9)


def test_k_mod_rejects_unknown_input():
    with pytest.raises(ValueError):
        k_mod(4, "medium-term")
    with pytest.raises(ValueError):
        k_mod(1, "for a while")


def test_gamma_M_distinguishes_glulam_from_solid():
    assert gamma_M_for(Material.resolve("C24")) == pytest.approx(1.3)
    assert gamma_M_for(Material.resolve("GL24h")) == pytest.approx(1.25)


def test_k_h_raises_strength_only_for_shallow_sections():
    solid = Material.resolve("C24")
    assert k_h_bending(solid, 0.24) == pytest.approx(1.0)
    assert k_h_bending(solid, 0.10) == pytest.approx(min(1.3, (0.150 / 0.10) ** 0.2))
    assert k_h_bending(solid, 0.0) == pytest.approx(1.0)


# --- the checks ----------------------------------------------------------

def test_size_factor_is_opt_in_and_raises_bending_strength():
    """RFEM's add-on leaves k_h off by default; so do we (see design-checks.md)."""
    model = FakeModel(section=FakeSection(width=0.08, height=0.10))
    member, result = model.members[0], FakeResult(moment_y=1.0)
    plain = check_member(model, member, result, DesignAssumptions())
    sized = check_member(model, member, result, DesignAssumptions(size_factor=True))
    k_h = (0.150 / 0.10) ** 0.2
    assert ratio_of(plain, "bending") == pytest.approx(ratio_of(sized, "bending") * k_h, rel=1e-9)
    assert "k_h=1.000" in plain.governing.detail
    assert "not applied" in " ".join(DesignAssumptions().describe())


def test_bending_matches_hand_calculation():
    member_check = check(moment_y=15.0)
    sigma = 15.0 / 0.001152                      # kN/m2
    f_md = 0.8 * 24.0 * MPA_TO_KN_M2 / 1.3       # kN/m2
    assert ratio_of(member_check, "bending") == pytest.approx(sigma / f_md, rel=1e-9)
    assert member_check.governing.name == "bending"
    assert member_check.governing.clause == "6.1.6"
    assert member_check.passes


def test_shear_uses_the_rectangular_factor():
    member_check = check(shear_z=12.0)
    tau = 1.5 * 12.0 / 0.0288
    f_vd = 0.8 * 4.0 * MPA_TO_KN_M2 / 1.3
    assert ratio_of(member_check, "shear") == pytest.approx(tau / f_vd, rel=1e-9)


def test_tension_and_compression_pick_the_right_strength():
    tension = check(axial=50.0)
    assert ratio_of(tension, "tension parallel") == pytest.approx(
        (50.0 / 0.0288) / (0.8 * 14.0 * MPA_TO_KN_M2 / 1.3), rel=1e-9
    )
    compression = check(axial=-50.0)
    assert ratio_of(compression, "compression parallel") == pytest.approx(
        (50.0 / 0.0288) / (0.8 * 21.0 * MPA_TO_KN_M2 / 1.3), rel=1e-9
    )


def test_biaxial_bending_applies_k_m():
    member_check = check(moment_y=10.0, moment_z=4.0)
    f_md = 0.8 * 24.0 * MPA_TO_KN_M2 / 1.3
    r_y = (10.0 / 0.001152) / f_md
    r_z = (4.0 / 0.000576) / f_md
    expected = max(r_y + 0.7 * r_z, 0.7 * r_y + r_z)
    assert ratio_of(member_check, "bending") == pytest.approx(expected, rel=1e-9)


def test_bending_plus_tension_is_linear():
    member_check = check(axial=50.0, moment_y=10.0)
    combined = ratio_of(member_check, "bending + tension")
    assert combined == pytest.approx(
        ratio_of(member_check, "tension parallel") + ratio_of(member_check, "bending"), rel=1e-9
    )
    assert member_check.governing.name == "bending + tension"


def test_bending_plus_compression_squares_the_axial_term():
    member_check = check(axial=-50.0, moment_y=10.0)
    axial_ratio = ratio_of(member_check, "compression parallel")
    combined = ratio_of(member_check, "bending + compression")
    assert combined == pytest.approx(axial_ratio ** 2 + ratio_of(member_check, "bending"), rel=1e-9)


def test_overload_is_reported_as_failing():
    member_check = check(moment_y=60.0)
    assert member_check.ratio > 1.0
    assert not member_check.passes


def test_unloaded_member_yields_no_silent_pass():
    member_check = check()
    assert member_check.checks == []
    assert member_check.notes
    assert "no check applicable" in member_check.notes[0]


def test_missing_section_is_noted_not_crashed():
    model = FakeModel()
    model.sections = []
    member_check = check_member(model, model.members[0], FakeResult(moment_y=10.0))
    assert member_check.checks == []
    assert "no section" in member_check.notes[0]


def test_assumed_material_is_flagged():
    model = FakeModel(grade="NotAGrade")
    member_check = check_member(model, model.members[0], FakeResult(moment_y=10.0))
    assert any("assumed" in note for note in member_check.notes)


def test_glulam_uses_its_own_partial_factor():
    model = FakeModel(grade="GL24h")
    member_check = check_member(model, model.members[0], FakeResult(moment_y=15.0), DesignAssumptions())
    assert member_check.gamma_M == pytest.approx(1.25)


def test_assumptions_are_carried_and_described():
    assumptions = DesignAssumptions(service_class=3, load_duration="permanent")
    model = FakeModel()
    member_check = check_member(model, model.members[0], FakeResult(moment_y=10.0), assumptions)
    assert member_check.k_mod == pytest.approx(0.5)
    text = "\n".join(assumptions.describe())
    assert "Service class:      3" in text
    assert "buckling" in text


def test_duration_is_inferred_from_the_load_case_and_recorded():
    class Case:
        id = 7
        action_category = "SNOW"

    assumptions = DesignAssumptions()
    model = FakeModel()
    member_check = check_member(model, model.members[0], FakeResult(moment_y=10.0), assumptions, Case())
    assert member_check.k_mod == pytest.approx(0.9)           # short-term, SC1
    assert assumptions.inferred_durations[7] == "short-term"
    assert "Inferred durations" in "\n".join(assumptions.describe())


def test_worst_per_member_keeps_only_the_governing_sample():
    model = FakeModel()
    samples = [
        check_member(model, model.members[0], FakeResult(position=0.0, moment_y=5.0)),
        check_member(model, model.members[0], FakeResult(position=0.5, moment_y=15.0)),
        check_member(model, model.members[0], FakeResult(position=1.0, moment_y=2.0)),
    ]
    worst = worst_per_member(samples)
    assert len(worst) == 1
    assert worst[0].position == pytest.approx(0.5)
