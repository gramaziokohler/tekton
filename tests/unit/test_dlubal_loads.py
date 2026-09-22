"""Loading must travel through the neutral model, not a backend-local catalogue.

Otherwise the same StructuralModel produces different loading in different
backends, which defeats the point of having a neutral layer.
"""

import pytest
from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralPointLoad
from compas_timber_fea.core.releases import LoadCombination

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")

from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper  # noqa: E402


@pytest.fixture
def mapper():
    return LoadMapper(rfem.loading, Loads=rfem.loads)


def test_load_cases_come_from_the_model(mapper):
    cases = [
        StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True),
        StructuralLoadCase(id=2, name="Snow", action_category="SNOW"),
    ]

    objects = mapper.map_load_cases(cases)

    # First object is the analysis settings the cases reference.
    settings, first, second = objects
    assert settings.no == 1
    assert (first.no, first.name) == (1, "Self-Weight")
    assert first.self_weight_active is True
    assert (second.no, second.name) == (2, "Snow")
    assert second.self_weight_active is False


def test_action_category_reaches_the_load_case(mapper):
    """The category drives RFEM's combination wizard, so it must not be hardcoded."""
    permanent = mapper.map_load_cases([StructuralLoadCase(id=1, name="G", action_category="PERMANENT")])[1]
    snow = mapper.map_load_cases([StructuralLoadCase(id=2, name="S", action_category="SNOW")])[1]

    assert permanent.action_category != snow.action_category


def test_point_load_carries_the_full_vector(mapper):
    """Vectors rotate into Dlubal's Z-down space: down (-z) becomes +z there - and kN become N."""
    load = StructuralPointLoad(id=1, node_id=7, load_case_id=2, force=Vector(1.0, 0.0, -5.0), moment=Vector(0.0, 2.0, 0.0))

    proto = mapper.map_point_load(load)

    assert list(proto.nodes) == [7]
    assert proto.load_case == 2
    assert proto.components_force_x == 1000.0
    assert proto.components_force_z == 5000.0
    assert proto.components_moment_y == -2000.0


def test_member_load_emits_one_object_per_direction(mapper):
    """RFEM applies a magnitude along one direction, so a vector needs splitting."""
    load = StructuralMemberLoad(id=1, member_id=3, load_case_id=1, force=Vector(0.0, 0.0, -2.5))

    protos = mapper.map_member_load(load)

    assert len(protos) == 1
    assert list(protos[0].members) == [3]
    # Down in the neutral Z-up world is +z in Dlubal's Z-down world; kN/m -> N/m.
    assert protos[0].magnitude == 2500.0
    assert protos[0].load_case == 1


def test_member_load_with_two_components_emits_two_objects(mapper):
    load = StructuralMemberLoad(id=1, member_id=3, load_case_id=1, force=Vector(1.0, 0.0, -2.5))

    protos = mapper.map_member_load(load)

    assert len(protos) == 2
    assert {p.magnitude for p in protos} == {1000.0, 2500.0}
    # Different global directions, so the enum values must differ.
    assert protos[0].load_direction != protos[1].load_direction


def test_zero_components_produce_no_load(mapper):
    load = StructuralMemberLoad(id=1, member_id=3, load_case_id=1, force=Vector(0.0, 0.0, 0.0))

    assert mapper.map_member_load(load) == []


def test_load_ids_are_unique_across_calls(mapper):
    first = mapper.map_point_load(StructuralPointLoad(id=1, node_id=1, load_case_id=1, force=Vector(0, 0, -1)))
    second = mapper.map_point_load(StructuralPointLoad(id=2, node_id=2, load_case_id=1, force=Vector(0, 0, -1)))

    assert first.no != second.no


def test_load_combination_carries_its_factors(mapper):
    combination = LoadCombination(id=1, name="ULS-1", factors={1: 1.35, 2: 1.5})

    proto = mapper.map_load_combination(combination)

    assert proto.no == 1
    assert proto.name == "ULS-1"
    rows = list(proto.items.rows)
    assert [(row.load_case, row.factor) for row in rows] == [(1, 1.35), (2, 1.5)]


def test_unknown_action_category_does_not_crash(mapper):
    """An unmapped category must degrade gracefully, not abort the export."""
    case = mapper.map_load_cases([StructuralLoadCase(id=1, name="X", action_category="SEISMIC")])[1]

    assert case.no == 1


def test_combinations_get_one_design_situation_per_type(mapper):
    """RFEM refuses to solve a combination outside a design situation; the add-on designs only ULS ones."""
    combinations = [
        LoadCombination(id=1, name="ULS-1", factors={1: 1.35}, combination_type="ULS"),
        LoadCombination(id=2, name="ULS-2", factors={1: 1.35, 2: 1.5}, combination_type="ULS"),
        LoadCombination(id=3, name="SLS", factors={1: 1.0, 2: 1.0}, combination_type="SLS_CHARACTERISTIC"),
    ]
    situations = mapper.map_design_situations(combinations)

    assert [s.no for s in situations] == [1, 2]
    assert situations[0].active_for_timber_design and not situations[1].active_for_timber_design
    assert mapper.map_load_combination(combinations[1]).design_situation == 1
    assert mapper.map_load_combination(combinations[2]).design_situation == 2
    assert mapper.map_load_combination(combinations[2]).to_solve


def test_no_combinations_means_no_design_situations(mapper):
    assert mapper.map_design_situations([]) == []
