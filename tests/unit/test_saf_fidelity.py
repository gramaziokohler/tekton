"""What a SAF export cannot carry, it has to say out loud.

The exporter writes seven sheets: materials, sections, nodes, members, point
supports, a load group and load cases. It does not write member hinges, it
hardcodes `It = 0.0`, and it writes load *cases* without the loads in them.

That combination is the one genuinely dangerous shape in this project: the file
opens cleanly in any SAF tool, carries our geometry and our member names, and
is a **stiffer structure carrying nothing**. A pinned timber frame arrives
fully rigid. Nobody is warned, because nothing failed.

So until the missing sheets exist, the export reports what it dropped - and
refuses outright when the loss changes the structure rather than merely
emptying it. The distinction:

* **releases** change the answer. A frame exported without them is a different
  structure, and silently so. Refuse.
* **loads** make the answer empty rather than wrong - the engineer sees a model
  with no load cases filled in, which is obvious on sight. Warn.
"""

import os
import tempfile

import pytest

from compas.geometry import Point

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.releases import MemberRelease

pytest.importorskip("pandas", reason="SAF export needs pandas")

from compas_saf.exporter.saf import SAFExporter  # noqa: E402
from compas_saf.exporter.saf import UnsupportedModel  # noqa: E402
from compas_saf.exporter.saf import fidelity_report  # noqa: E402


def _model():
    """A beam on two supports. Nothing a SAF export cannot carry."""
    model = StructuralModel()
    model.materials[1] = "C24"
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(4, 0, 0)))
    model.sections.append(StructuralSection(id=1, name="R 0.1/0.2", material_id=1, width=0.1, height=0.2))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=2, section_id=1))
    model.supports.append(StructuralSupport(id=1, nodes=[1]))
    model.supports.append(StructuralSupport(id=2, nodes=[2]))
    return model


def _path(name="m.xlsx"):
    return os.path.join(tempfile.mkdtemp(), name)


# --- the report -----------------------------------------------------------

def test_a_plain_model_loses_nothing_structural():
    report = fidelity_report(_model())

    assert report.refuses == []


def test_a_release_is_a_refusal():
    """The dangerous case: it would arrive as a rigid frame."""
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()

    report = fidelity_report(model)

    assert report.refuses
    assert any("release" in reason.lower() for reason in report.refuses)


def test_the_refusal_says_how_many_and_which_members():
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()

    reason = " ".join(fidelity_report(model).refuses)

    assert "1" in reason


def test_a_spring_release_is_refused_too():
    """A finite stiffness is as lost as a free DOF, and less obvious."""
    model = _model()
    model.members[0].release_end = MemberRelease(ry=5000.0)

    assert fidelity_report(model).refuses


def test_loads_are_a_warning_not_a_refusal():
    """An empty load case is visible on sight; a rigid frame is not."""
    model = _model()
    model.load_cases.append(StructuralLoadCase(id=1, name="G"))
    model.member_loads.append(StructuralMemberLoad(id=1, member_id=1, load_case_id=1))

    report = fidelity_report(model)

    assert report.refuses == []
    assert any("load" in warning.lower() for warning in report.warnings)


def test_torsion_is_always_a_warning():
    """`It = 0.0` is hardcoded, so every export loses it."""
    assert any("torsion" in w.lower() for w in fidelity_report(_model()).warnings)


def test_surfaces_are_a_refusal():
    """No surface sheet is written at all, so a plate model would export as
    its beams alone - a different structure, not an emptier one."""
    from compas_timber_fea.core.model import StructuralSurface
    from compas_timber_fea.core.model import StructuralThickness

    model = _model()
    model.thicknesses.append(StructuralThickness(id=1, name="t", material_id=1, thickness=0.2))
    model.surfaces.append(StructuralSurface(id=1, nodes=[1, 2], thickness_id=1))

    assert any("surface" in reason.lower() for reason in fidelity_report(model).refuses)


def test_line_supports_are_a_refusal():
    from compas_timber_fea.core.model import StructuralLineSupport

    model = _model()
    model.line_supports.append(StructuralLineSupport(id=1, nodes=[1, 2]))

    assert any("line support" in reason.lower() for reason in fidelity_report(model).refuses)


def test_the_report_reads_as_prose():
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()

    text = fidelity_report(model).describe()

    assert "SAF" in text
    assert "release" in text.lower()


# --- the export itself ----------------------------------------------------

def test_a_plain_model_exports():
    path = _path()

    assert SAFExporter(_model()).export(path) is True
    assert os.path.isfile(path)


def test_a_model_with_releases_is_refused():
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()
    path = _path()

    with pytest.raises(UnsupportedModel, match="release"):
        SAFExporter(model).export(path)


def test_a_refused_export_writes_no_file():
    """Half a file is worse than none: someone would open it."""
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()
    path = _path()

    with pytest.raises(UnsupportedModel):
        SAFExporter(model).export(path)

    assert not os.path.exists(path)


def test_the_refusal_names_what_to_do():
    """An error that only says no is a dead end."""
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()

    with pytest.raises(UnsupportedModel) as caught:
        SAFExporter(model).export(_path())

    message = str(caught.value).lower()
    assert "rfem" in message or "opensees" in message


def test_the_refusal_can_be_overridden_deliberately():
    """Someone who wants the geometry and knows the rest is missing should be
    able to say so - but only by saying so."""
    model = _model()
    model.members[0].release_start = MemberRelease.pinned()
    path = _path()

    assert SAFExporter(model, allow_loss=True).export(path) is True
    assert os.path.isfile(path)


def test_warnings_do_not_block_an_export():
    model = _model()
    model.load_cases.append(StructuralLoadCase(id=1, name="G"))
    model.member_loads.append(StructuralMemberLoad(id=1, member_id=1, load_case_id=1))

    assert SAFExporter(model).export(_path()) is True


def test_the_exporter_reports_its_losses_on_the_object():
    """So a caller - the worker, a component - can show them rather than
    relying on whatever was printed to a console nobody is reading."""
    model = _model()
    model.load_cases.append(StructuralLoadCase(id=1, name="G"))
    model.member_loads.append(StructuralMemberLoad(id=1, member_id=1, load_case_id=1))

    exporter = SAFExporter(model)
    exporter.export(_path())

    assert any("load" in w.lower() for w in exporter.report.warnings)
