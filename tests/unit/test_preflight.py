"""Preflight: catch the predictable failure modes before analysis.

The reference failure is the repo's own history - every committed fixture used
to push a support-less model, and RFEM was asked to solve a mechanism without
anyone noticing.
"""

from compas.data import json_load
from compas.geometry import Point

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.preflight import preflight
from compas_timber_fea.translator import TimberToStructural


def _minimal_model():
    model = StructuralModel()
    model.materials[1] = "C24"
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(0, 0, 3)))
    model.sections.append(StructuralSection(id=1, name="R_M1 0.1/0.2", material_id=1, width=0.1, height=0.2))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=2, section_id=1))
    model.supports.append(StructuralSupport(id=1, nodes=[1]))
    return model


def test_clean_model_passes():
    report = preflight(_minimal_model())

    assert report.ok
    assert report.warnings == []


def test_missing_supports_is_an_error():
    model = _minimal_model()
    model.supports = []

    report = preflight(model)

    assert not report.ok
    assert any("no supports" in message for message in report.errors)


def test_dangling_member_node_is_an_error():
    model = _minimal_model()
    model.members[0].node_end = 99

    report = preflight(model)

    assert any("missing end node 99" in message for message in report.errors)


def test_missing_material_is_an_error():
    model = _minimal_model()
    model.materials = {}

    report = preflight(model)

    assert any("missing material" in message for message in report.errors)


def test_load_on_unknown_load_case_is_an_error():
    from compas.geometry import Vector

    model = _minimal_model()
    model.load_cases.append(StructuralLoadCase(id=1, name="SW", self_weight=True))
    model.member_loads.append(StructuralMemberLoad(id=1, member_id=1, load_case_id=7, force=Vector(0, 0, -1)))

    report = preflight(model)

    assert any("missing load case 7" in message for message in report.errors)


def test_disconnected_parts_are_a_warning():
    model = _minimal_model()
    model.nodes.append(StructuralNode(id=3, point=Point(5, 0, 0)))
    model.nodes.append(StructuralNode(id=4, point=Point(5, 0, 3)))
    model.members.append(StructuralMember(id=2, node_start=3, node_end=4, section_id=1))

    report = preflight(model)

    assert any("disconnected parts" in message for message in report.warnings)


def test_the_committed_fixture_fails_preflight_for_missing_supports():
    """The sticks fixture has no support_points - preflight must say so."""
    structural_model = TimberToStructural().translate(json_load("tests/timber_model_sticks.json"))

    report = preflight(structural_model)

    assert any("no supports" in message for message in report.errors)
