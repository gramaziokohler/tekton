"""WP3: assembling combination results from load case results.

The anchor is an equivalence: a combination assembled from a solved case
must equal the same load solved directly. If that holds to machine
precision, the superposition is right; if it does not, everything built on
combinations is quietly wrong.
"""

import pytest

from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.materials import Material
from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralSurfaceLoad
from compas_timber_fea.core.model import StructuralThickness
from compas_timber_fea.core.releases import LoadCombination
from compas_timber_fea.core.superposition import COMBINATION_ID_BASE
from compas_timber_fea.core.superposition import SuperpositionError
from compas_timber_fea.core.superposition import combine_all
from compas_timber_fea.core.superposition import combine_results
from compas_opensees import run_model


def plate(pressure=None, thickness=0.2, self_weight=False, case_id=1, side=4.0, divisions=8):
    outline = []
    for i in range(divisions):
        outline.append((side * i / divisions, 0.0))
    for j in range(divisions):
        outline.append((side, side * j / divisions))
    for i in range(divisions, 0, -1):
        outline.append((side * i / divisions, side))
    for j in range(divisions, 0, -1):
        outline.append((0.0, side * j / divisions))

    model = StructuralModel()
    ids = {index: point for index, point in enumerate(outline, start=1)}
    model.nodes = [StructuralNode(id=i, point=Point(x, y, 0.0)) for i, (x, y) in ids.items()]
    model.materials = {1: Material.resolve("C24")}
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=thickness)]
    model.surfaces = [StructuralSurface(id=1, nodes=list(ids), thickness_id=1)]
    model.supports = [StructuralSupport(id=1, nodes=list(ids), rx=0.0, ry=0.0, rz=0.0)]
    model.load_cases = [StructuralLoadCase(id=case_id, name="case", self_weight=self_weight)]
    if pressure is not None:
        model.surface_loads = [StructuralSurfaceLoad(
            id=1, surface_id=1, load_case_id=case_id, pressure=Vector(0, 0, pressure))]
    return model


def worst_deflection(result_set):
    return max(abs(s.displacement.z) for s in result_set.surface_results[1])


def reaction_total(result_set):
    return sum(n.reaction_force.z for n in result_set.node_results.values() if n.reaction_force)


def fake_model():
    """A model with hand-written results - no solver, exact numbers."""
    model = StructuralModel()
    model.load_cases = [StructuralLoadCase(id=1, name="G"), StructuralLoadCase(id=2, name="Q")]
    for case_id, value in ((1, 1.0), (2, 10.0)):
        model.results[case_id] = StructuralResultSet(
            load_case_id=case_id,
            node_results={7: StructuralNodeResult(
                node_id=7, load_case_id=case_id,
                displacement=Vector(0, 0, -value),
                rotation=Vector(0, value, 0),
                reaction_force=Vector(0, 0, value),
                reaction_moment=Vector(value, 0, 0))},
            member_results={3: [StructuralMemberResult(
                member_id=3, load_case_id=case_id, position=0.5,
                axial=value, shear_z=2 * value, moment_y=3 * value)]},
        )
    return model


# --- the equivalence that matters ---------------------------------------

def test_a_scaled_combination_equals_the_same_load_solved_directly():
    scaled = plate(pressure=-1.0)
    run_model(scaled)
    combined = combine_results(scaled, LoadCombination(id=1, name="1.5x", factors={1: 1.5}))

    direct = plate(pressure=-1.5)
    run_model(direct)

    assert worst_deflection(combined) == pytest.approx(
        worst_deflection(direct.results[1]), rel=1e-9)
    assert reaction_total(combined) == pytest.approx(
        reaction_total(direct.results[1]), rel=1e-9)


def test_two_cases_add_up_to_their_sum_solved_directly():
    parts = plate(pressure=-1.0)
    run_model(parts)
    combined = combine_results(parts, LoadCombination(id=1, name="2x", factors={1: 2.0}))

    direct = plate(pressure=-2.0)
    run_model(direct)
    assert worst_deflection(combined) == pytest.approx(worst_deflection(direct.results[1]), rel=1e-9)


# --- the arithmetic, on exact numbers -----------------------------------

def test_node_results_are_factored_and_summed():
    model = fake_model()
    combined = combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.35, 2: 1.5}))
    node = combined.node_results[7]
    assert node.displacement.z == pytest.approx(-(1.35 * 1.0 + 1.5 * 10.0))
    assert node.reaction_force.z == pytest.approx(1.35 * 1.0 + 1.5 * 10.0)
    assert node.reaction_moment.x == pytest.approx(1.35 * 1.0 + 1.5 * 10.0)
    assert node.rotation.y == pytest.approx(1.35 * 1.0 + 1.5 * 10.0)


def test_member_forces_are_factored_and_summed():
    model = fake_model()
    combined = combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.35, 2: 1.5}))
    sample = combined.member_results[3][0]
    total = 1.35 * 1.0 + 1.5 * 10.0
    assert sample.axial == pytest.approx(total)
    assert sample.shear_z == pytest.approx(2 * total)
    assert sample.moment_y == pytest.approx(3 * total)
    assert sample.position == pytest.approx(0.5)


def test_a_zero_factor_contributes_nothing():
    model = fake_model()
    combined = combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.0, 2: 0.0}))
    assert combined.node_results[7].displacement.z == pytest.approx(-1.0)


def test_a_negative_factor_subtracts():
    """Uplift: wind against self-weight."""
    model = fake_model()
    combined = combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.0, 2: -0.5}))
    assert combined.node_results[7].displacement.z == pytest.approx(-(1.0 - 0.5 * 10.0))


# --- provenance and refusal ---------------------------------------------

def test_the_result_records_what_it_was_made_from():
    model = fake_model()
    combined = combine_results(model, LoadCombination(
        id=4, name="ULS", factors={1: 1.35, 2: 1.5}, combination_type="ULS"))
    assert combined.metadata["source"] == "superposition"
    assert combined.metadata["combination_type"] == "ULS"
    assert combined.metadata["factors"] == {"1": 1.35, "2": 1.5}
    assert combined.metadata["linear_only"] is True
    assert combined.load_case_id == COMBINATION_ID_BASE + 4


def test_a_missing_load_case_is_refused_not_skipped():
    """Dropping a case would understate the combination - the one direction
    an engineer must never be surprised in."""
    model = fake_model()
    with pytest.raises(SuperpositionError, match="not solved"):
        combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.35, 99: 1.5}))


def test_an_empty_combination_is_refused():
    with pytest.raises(SuperpositionError, match="no factors"):
        combine_results(fake_model(), LoadCombination(id=1, name="c", factors={}))


def test_mismatched_sampling_positions_are_refused():
    model = fake_model()
    model.results[2].member_results[3][0].position = 0.25
    with pytest.raises(SuperpositionError, match="different positions"):
        combine_results(model, LoadCombination(id=1, name="c", factors={1: 1.0, 2: 1.0}))


# --- the bulk path -------------------------------------------------------

def test_combine_all_writes_into_the_model_so_everything_downstream_sees_it():
    model = fake_model()
    model.load_combinations = [
        LoadCombination(id=1, name="ULS", factors={1: 1.35, 2: 1.5}),
        LoadCombination(id=2, name="SLS", factors={1: 1.0, 2: 1.0}),
    ]
    out = combine_all(model)
    assert len(out) == 2
    for result_id in out:
        assert result_id in model.results
    assert 1 in model.results and 2 in model.results       # the cases survive


def test_combine_all_can_leave_the_model_alone():
    model = fake_model()
    model.load_combinations = [LoadCombination(id=1, name="ULS", factors={1: 1.35})]
    before = set(model.results)
    combine_all(model, into_model=False)
    assert set(model.results) == before
