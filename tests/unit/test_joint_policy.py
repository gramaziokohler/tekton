"""The joint policy is the engineering content of the bridge.

It decides how a physical timber joint becomes a mechanical end condition, and
must be overridable per type and per instance, with every decision traceable.
"""

import math

import pytest
from compas.data import json_load

from compas_timber_fea.core.joint_policy import JointPolicy
from compas_timber_fea.core.joint_policy import policy_from_connector_mode
from compas_timber_fea.core.releases import FREE
from compas_timber_fea.core.releases import RIGID
from compas_timber_fea.core.releases import MemberRelease
from compas_timber_fea.translator import TimberToStructural

STICKS = "tests/timber_model_sticks.json"


class FakeJoint:
    """Stands in for a compas_timber joint; only type name and guid matter here."""

    def __init__(self, guid="joint-1"):
        self.guid = guid


class TButtJoint(FakeJoint):
    pass


class XLapJoint(FakeJoint):
    pass


def test_pinned_release_frees_bending_but_keeps_torsion():
    release = MemberRelease.pinned()

    assert release.released_dofs() == ("ry", "rz")
    assert release.ux == RIGID
    assert release.rx == RIGID
    assert release.ry == FREE
    assert not release.is_rigid()


def test_rigid_release_frees_nothing():
    release = MemberRelease.rigid()

    assert release.is_rigid()
    assert release.released_dofs() == ()


def test_default_is_conservative_hinge():
    """Timber connections rarely transfer bending, so the default must be a hinge."""
    policy = JointPolicy.conservative()

    assert policy.release_for(TButtJoint()).released_dofs() == ("ry", "rz")
    assert policy.release_for(None).released_dofs() == ("ry", "rz")


def test_type_rule_overrides_the_default():
    policy = JointPolicy.conservative().override_type("XLapJoint", MemberRelease.rigid())

    assert policy.release_for(XLapJoint()).is_rigid()
    assert not policy.release_for(TButtJoint()).is_rigid()


def test_instance_rule_overrides_the_type_rule():
    policy = JointPolicy.conservative().override_type("TButtJoint", MemberRelease.rigid())
    policy.override_instance("joint-special", MemberRelease.pinned())

    assert policy.release_for(TButtJoint(guid="joint-normal")).is_rigid()
    assert not policy.release_for(TButtJoint(guid="joint-special")).is_rigid()


def test_spring_stiffness_is_representable():
    """EC5 connection stiffness is a finite spring, not just rigid or free."""
    springy = MemberRelease(ry=1500.0, rz=1500.0, name="Kser-based")
    policy = JointPolicy.conservative().override_type("TButtJoint", springy)

    release = policy.release_for(TButtJoint())
    assert release.ry == 1500.0
    assert release.released_dofs() == ("ry", "rz")
    assert not release.is_rigid()


def test_decision_is_explained_with_its_basis():
    policy = JointPolicy.conservative().override_type("XLapJoint", MemberRelease.rigid())

    assert "type rule" in policy.describe_for(XLapJoint())
    assert "policy default" in policy.describe_for(TButtJoint())

    policy.override_instance("j9", MemberRelease.pinned())
    assert "instance override" in policy.describe_for(XLapJoint(guid="j9"))


def test_connector_mode_maps_to_a_policy():
    assert policy_from_connector_mode("rigid").release_for(TButtJoint()).is_rigid()
    assert not policy_from_connector_mode("coupling").release_for(TButtJoint()).is_rigid()


@pytest.fixture
def sticks():
    return json_load(STICKS)


def test_policy_changes_translated_connectors(sticks):
    """The same model must yield hinges or rigid links depending on the policy."""
    rigid_model = TimberToStructural(joint_policy=JointPolicy.rigid()).translate(sticks)
    hinged_model = TimberToStructural(joint_policy=JointPolicy.conservative()).translate(json_load(STICKS))

    rigid_connectors = [m for m in rigid_model.members if m.source_element_type == "connector"]
    hinged_connectors = [m for m in hinged_model.members if m.source_element_type == "connector"]

    assert rigid_connectors and hinged_connectors
    assert all(m.member_type == "RIGID" for m in rigid_connectors)
    assert all(m.member_type == "COUPLING" for m in hinged_connectors)
    # A hinge sits on exactly one end: both hinged would be a pendulum bar.
    assert all((m.release_start is None) != (m.release_end is None) for m in hinged_connectors)
    assert all(m.release_start is None and m.release_end is None for m in rigid_connectors)


def test_translated_connectors_carry_their_source_joint(sticks):
    model = TimberToStructural(joint_policy=JointPolicy.conservative()).translate(sticks)

    connectors = [m for m in model.members if m.source_element_type == "connector"]
    assert connectors
    assert all(m.source_joint_start for m in connectors), "connector lost its originating joint"


def test_translation_reports_joint_decisions(sticks):
    translator = TimberToStructural(joint_policy=JointPolicy.default_catalogue())
    translator.translate(sticks)

    joint_entries = [entry for entry in translator.report if "Joint" in entry]
    assert joint_entries, "joint idealisation was not reported"
    assert any("type rule" in entry for entry in joint_entries)


def test_released_connector_survives_serialization(sticks, tmp_path):
    from compas_timber_fea.core.model import StructuralModel

    model = TimberToStructural(joint_policy=JointPolicy.conservative()).translate(sticks)
    path = tmp_path / "model.json"
    model.to_json(path)

    loaded = StructuralModel.from_json(path)
    connector = next(m for m in loaded.members if m.source_element_type == "connector")

    release = connector.release_start or connector.release_end
    assert isinstance(release, MemberRelease)
    assert release.released_dofs() == ("ry", "rz")
    assert release.ux == math.inf
