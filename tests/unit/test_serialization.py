"""The neutral model must survive a round-trip to disk.

Without this, the model cannot be handed to an engineer, diffed between design
iterations, or used to map results back onto source elements in a later session.
"""

import math

from compas.geometry import Point
from compas.geometry import Vector

from tekton_core.core.model import StructuralLoadCase
from tekton_core.core.model import StructuralMember
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralSection
from tekton_core.core.model import StructuralSupport
from tekton_core.core.releases import LoadCombination
from tekton_core.core.releases import MemberRelease


def _model():
    model = StructuralModel()
    model.materials[1] = "C24"
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0), source_node_id="n1"))
    model.nodes.append(StructuralNode(id=2, point=Point(0, 0, 3.5)))
    model.sections.append(StructuralSection(id=1, name="R_M1 0.1/0.2", material_id=1, width=0.1, height=0.2))
    model.members.append(
        StructuralMember(
            id=1,
            node_start=1,
            node_end=2,
            section_id=1,
            orientation_vector=Vector(0, 1, 0),
            release_start=MemberRelease.pinned(),
            source_element_id="beam-guid-1",
            source_joint_start="joint-guid-9",
        )
    )
    model.supports.append(StructuralSupport(id=1, nodes=[1], rx=0.0, ry=0.0, rz=0.0))
    model.load_cases.append(StructuralLoadCase(id=1, name="Self-Weight", self_weight=True))
    model.load_combinations.append(LoadCombination(id=1, name="ULS-1", factors={1: 1.35}))
    return model


def test_roundtrip_preserves_geometry(tmp_path):
    path = tmp_path / "model.json"
    _model().to_json(path)

    loaded = StructuralModel.from_json(path)

    assert isinstance(loaded.nodes[0].point, Point)
    assert loaded.nodes[1].point.z == 3.5
    assert isinstance(loaded.members[0].orientation_vector, Vector)
    assert list(loaded.members[0].orientation_vector) == [0, 1, 0]


def test_roundtrip_preserves_infinite_stiffness(tmp_path):
    """inf marks a restrained DOF; plain JSON cannot express it."""
    path = tmp_path / "model.json"
    _model().to_json(path)

    loaded = StructuralModel.from_json(path)

    support = loaded.supports[0]
    assert support.ux == math.inf
    assert support.uy == math.inf
    assert support.rx == 0.0


def test_roundtrip_preserves_releases(tmp_path):
    path = tmp_path / "model.json"
    _model().to_json(path)

    loaded = StructuralModel.from_json(path)

    release = loaded.members[0].release_start
    assert isinstance(release, MemberRelease)
    assert release.released_dofs() == ("ry", "rz")
    assert release.ux == math.inf
    assert loaded.members[0].release_end is None


def test_roundtrip_preserves_integer_dict_keys(tmp_path):
    """materials and combination factors are keyed by int, which JSON stringifies."""
    path = tmp_path / "model.json"
    _model().to_json(path)

    loaded = StructuralModel.from_json(path)

    assert loaded.materials == {1: "C24"}
    assert loaded.load_combinations[0].factors == {1: 1.35}


def test_roundtrip_preserves_provenance(tmp_path):
    path = tmp_path / "model.json"
    _model().to_json(path)

    loaded = StructuralModel.from_json(path)

    member = loaded.members[0]
    assert member.source_element_id == "beam-guid-1"
    assert member.source_joint_start == "joint-guid-9"
    assert loaded.nodes[0].source_node_id == "n1"


def test_roundtrip_of_a_translated_model(tmp_path):
    """The real translator output, not just a hand-built model."""
    from compas.geometry import Line
    from compas_timber.elements import Beam
    from compas_timber.model import TimberModel

    from tekton_core.translator import TimberToStructural

    timber_model = TimberModel()
    timber_model.add_element(Beam.from_centerline(Line((0, 0, 0), (3, 0, 0)), width=0.1, height=0.2))
    structural_model = TimberToStructural().translate(timber_model)

    path = tmp_path / "translated.json"
    structural_model.to_json(path)
    loaded = StructuralModel.from_json(path)

    assert len(loaded.nodes) == len(structural_model.nodes)
    assert len(loaded.members) == len(structural_model.members)
    assert len(loaded.sections) == len(structural_model.sections)
    assert loaded.members[0].source_element_id == structural_model.members[0].source_element_id
