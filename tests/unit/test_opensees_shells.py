"""WP0b: plates through OpenSees - shells, loads, results.

The anchor is the Navier solution for a simply supported square plate under a
uniform load, ``w = 0.00406 q a^4 / D``. A shell element that is wired up
wrongly still produces plausible-looking numbers, so an independent closed
form is the only check worth having; mesh refinement must walk towards it.
"""

import pytest

from compas.geometry import Point

from compas_timber_fea.core.materials import Material
from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralThickness
from compas_opensees import run_model

GRAVITY = 9.81
SIDE = 4.0
THICKNESS = 0.2
NAVIER = 0.00406          # simply supported square plate, uniform load


def square_plate(target=0.35, grade="C24", thickness=THICKNESS, side=SIDE,
                 span_direction=None, pinned=True):
    """A square plate whose outline is already subdivided at the target length.

    The outline carries the support, so it has to be resolved: a plate
    supported only at its four corners is a different structure.
    """
    divisions = max(2, int(round(side / target)))
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
    model.materials = {1: Material.resolve(grade)}
    model.thicknesses = [StructuralThickness(id=1, name="t", material_id=1, thickness=thickness)]
    model.surfaces = [StructuralSurface(id=1, nodes=list(ids), thickness_id=1,
                                        span_direction=span_direction)]
    # Simply supported: translations held, rotations free.
    support = StructuralSupport(id=1, nodes=list(ids), rx=0.0, ry=0.0, rz=0.0) if pinned \
        else StructuralSupport(id=1, nodes=list(ids))
    model.supports = [support]
    model.load_cases = [StructuralLoadCase(id=1, name="SW", self_weight=True)]
    return model


def navier_deflection(model, side=SIDE, thickness=THICKNESS):
    material = model.materials[1]
    E = material.E0_mean * 1000.0                      # MPa -> kN/m2
    D = E * thickness ** 3 / (12 * (1 - material.poisson ** 2))
    q = material.density_mean * GRAVITY / 1000.0 * thickness
    return NAVIER * q * side ** 4 / D, q


# --- building ------------------------------------------------------------

def test_a_plate_model_builds_shells_instead_of_being_refused():
    model = square_plate(0.5)
    result = run_model(model)
    assert any("surface" in line for line in result.log)
    assert model.results[1].surface_results


def test_every_plate_node_gets_a_sample():
    model = square_plate(0.5)
    run_model(model)
    samples = model.results[1].surface_results[1]
    assert len({sample.metadata["node_tag"] for sample in samples}) == len(samples)
    assert any(sample.metadata["from_mesh"] for sample in samples)
    assert any(not sample.metadata["from_mesh"] for sample in samples)


def test_samples_carry_their_location():
    model = square_plate(0.5)
    run_model(model)
    for sample in model.results[1].surface_results[1]:
        assert sample.position is not None
        assert 0.0 - 1e-9 <= sample.position[0] <= SIDE + 1e-9


# --- the physics ---------------------------------------------------------

def test_reactions_carry_the_whole_self_weight():
    """The equilibrium check: a lost load would show up here and nowhere else."""
    model = square_plate(0.5)
    run_model(model)
    _, q = navier_deflection(model)
    total = sum(node.reaction_force.z for node in model.results[1].node_results.values()
                if node.reaction_force)
    assert total == pytest.approx(q * SIDE * SIDE, rel=1e-6)


@pytest.mark.parametrize("target,tolerance", [(0.5, 0.06), (0.35, 0.04), (0.25, 0.02)])
def test_deflection_approaches_the_navier_solution(target, tolerance):
    model = square_plate(target)
    run_model(model)
    expected, _ = navier_deflection(model)
    worst = max(abs(sample.displacement.z) for sample in model.results[1].surface_results[1])
    assert worst == pytest.approx(expected, rel=tolerance)


def test_refining_the_mesh_moves_towards_the_exact_solution():
    exact = None
    errors = []
    for target in (0.5, 0.25):
        model = square_plate(target)
        run_model(model)
        exact, _ = navier_deflection(model)
        worst = max(abs(s.displacement.z) for s in model.results[1].surface_results[1])
        errors.append(abs(worst - exact) / exact)
    assert errors[1] < errors[0]


def test_a_thicker_plate_deflects_less():
    thin = square_plate(0.5, thickness=0.15)
    thick = square_plate(0.5, thickness=0.25)
    run_model(thin)
    run_model(thick)
    worst_thin = max(abs(s.displacement.z) for s in thin.results[1].surface_results[1])
    worst_thick = max(abs(s.displacement.z) for s in thick.results[1].surface_results[1])
    assert worst_thick < worst_thin


# --- honesty -------------------------------------------------------------

def test_span_direction_is_reported_as_not_modelled():
    """Orthotropy does not survive OpenSees' plate path - the run must say so."""
    from compas.geometry import Vector

    model = square_plate(0.5, span_direction=Vector(1, 0, 0))
    result = run_model(model)
    assert any("span_direction" in line and "isotropic" in line for line in result.log)


def test_an_unoriented_plate_gets_no_such_warning():
    model = square_plate(0.5)
    result = run_model(model)
    assert not any("span_direction" in line for line in result.log)


def test_unknown_thickness_is_refused_before_anything_is_built():
    """Preflight already blocks this, and an error beats a warning here:
    a plate without a thickness has no stiffness, so the run would be
    meaningless rather than merely incomplete."""
    model = square_plate(0.5)
    model.surfaces[0].thickness_id = 99
    with pytest.raises(RuntimeError, match="missing thickness"):
        run_model(model)


# --- membrane forces and moments (WP0b-Rest) ---------------------------------

def one_way_plate(along="x", target=0.35):
    """The square plate supported on two opposite edges only: cylindrical bending."""
    model = square_plate(target)
    points = {node.id: node.point for node in model.nodes}
    coordinate = (lambda p: p.x) if along == "x" else (lambda p: p.y)
    support = model.supports[0]
    support.nodes = [i for i in support.nodes
                     if abs(coordinate(points[i])) < 1e-9 or abs(coordinate(points[i]) - SIDE) < 1e-9]
    return model


def centre_sample(model):
    return min(model.results[1].surface_results[1],
               key=lambda s: (s.position.x - SIDE / 2) ** 2 + (s.position.y - SIDE / 2) ** 2)


def test_centre_moments_of_the_simply_supported_plate():
    """m_x = m_y = 0.0368 q a^2 (nu = 0), sagging positive as RFEM reports it."""
    model = square_plate(0.35)
    run_model(model)
    _, q = navier_deflection(model)
    centre = centre_sample(model)
    assert centre.moment_x == pytest.approx(0.0368 * q * SIDE ** 2, rel=0.05)
    assert centre.moment_y == pytest.approx(centre.moment_x, rel=0.01)
    assert abs(centre.moment_xy) < 0.01 * centre.moment_x
    assert centre.membrane_force_x == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("along", ["x", "y"])
def test_one_way_plate_bends_about_one_axis_only(along):
    """q a^2 / 8 in the span direction, nothing across - the element-axis rotation must be right for every triangle."""
    model = one_way_plate(along)
    run_model(model)
    _, q = navier_deflection(model)
    centre = centre_sample(model)
    spanning, across = (centre.moment_x, centre.moment_y) if along == "x" else (centre.moment_y, centre.moment_x)
    assert spanning == pytest.approx(q * SIDE ** 2 / 8, rel=0.03)
    assert abs(across) < 0.01 * spanning
