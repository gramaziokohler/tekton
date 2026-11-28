"""How timber joints become mechanical end conditions.

This is the engineering content of the bridge, and the part a structural
engineer needs to see and be able to override. It is deliberately a separate,
serialisable object rather than logic buried in the translator: the mapping is
an assumption about the structure, not an implementation detail.

The default is conservative. Timber connections rarely transfer meaningful
bending, so unless a joint type is known to be rigid, it is modelled as a
hinge. Overriding is possible per joint type and per joint instance, and the
resulting decisions are reported so nothing is silently assumed.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import Optional

from tekton_core.core.releases import MemberRelease

#: Joint types modelled as fully continuous by default. Everything else falls
#: back to a hinge, which is the safe assumption for timber.
DEFAULT_RIGID_JOINT_TYPES = frozenset({
    "LMiterJoint",
    "XLapJoint",
    "THalfLapJoint",
    "LHalfLapJoint",
})


@dataclass
class PlateConnectionPolicy:
    """How plates are connected where they meet along an edge.

    compas_timber's plate surfaces do not share nodes, so without an explicit
    connection the plates are separate pieces and the model is a mechanism.
    Each connection gets a release from this policy: continuous, hinged, or
    springy.

    The default is a hinged edge. Timber panel joints (butt joints with
    fasteners, mitred edges) transfer shear and normal force but little
    bending, so assuming continuity would overestimate the structure's
    stiffness. Along an edge only rotation about the edge axis is meaningful,
    which is what :meth:`MemberRelease.hinged_edge` expresses.
    """

    default: MemberRelease = field(default_factory=MemberRelease.hinged_edge)
    by_type: Dict[str, MemberRelease] = field(default_factory=dict)
    by_instance: Dict[str, MemberRelease] = field(default_factory=dict)

    @classmethod
    def continuous(cls):
        """Plates act monolithically. Only right where panels are truly continuous."""
        return cls(default=MemberRelease.rigid())

    def release_for(self, joint) -> MemberRelease:
        """Return the end condition for a plate joint (or the default for None)."""
        if joint is None:
            return self.default

        guid = str(getattr(joint, "guid", "")) or None
        if guid and guid in self.by_instance:
            return self.by_instance[guid]

        joint_type = type(joint).__name__
        if joint_type in self.by_type:
            return self.by_type[joint_type]

        return self.default

    def override_type(self, joint_type: str, release: MemberRelease):
        self.by_type[joint_type] = release
        return self

    def override_instance(self, joint_guid: str, release: MemberRelease):
        self.by_instance[str(joint_guid)] = release
        return self


@dataclass
class JointPolicy:
    """Maps timber joint types to mechanical end conditions.

    Parameters
    ----------
    default : MemberRelease
        Applied when a joint type has no specific rule. Defaults to a hinge.
    by_type : dict
        Joint class name -> MemberRelease.
    by_instance : dict
        Joint guid (as str) -> MemberRelease. Takes precedence over by_type.
    """

    default: MemberRelease = field(default_factory=MemberRelease.pinned)
    by_type: Dict[str, MemberRelease] = field(default_factory=dict)
    by_instance: Dict[str, MemberRelease] = field(default_factory=dict)

    @classmethod
    def conservative(cls):
        """Every joint is a hinge. The safest starting point for timber."""
        return cls(default=MemberRelease.pinned())

    @classmethod
    def rigid(cls):
        """Every joint is continuous. Matches the previous 'rigid' connector mode."""
        return cls(default=MemberRelease.rigid())

    @classmethod
    def default_catalogue(cls):
        """Carpentry joints with interlocking geometry rigid, the rest hinged."""
        by_type = {name: MemberRelease.rigid(name=f"rigid ({name})") for name in DEFAULT_RIGID_JOINT_TYPES}
        return cls(default=MemberRelease.pinned(), by_type=by_type)

    def release_for(self, joint) -> MemberRelease:
        """Return the end condition for a joint instance (or the default for None)."""
        if joint is None:
            return self.default

        guid = str(getattr(joint, "guid", "")) or None
        if guid and guid in self.by_instance:
            return self.by_instance[guid]

        joint_type = type(joint).__name__
        if joint_type in self.by_type:
            return self.by_type[joint_type]

        return self.default

    def describe_for(self, joint) -> str:
        """Human-readable reason for the decision, used in the assumptions report."""
        release = self.release_for(joint)
        joint_type = type(joint).__name__ if joint is not None else "unresolved candidate"
        guid = str(getattr(joint, "guid", "")) if joint is not None else ""

        if guid and guid in self.by_instance:
            basis = "instance override"
        elif joint_type in self.by_type:
            basis = "type rule"
        else:
            basis = "policy default"

        kind = "rigid" if release.is_rigid() else "released " + "/".join(release.released_dofs())
        return f"{joint_type}: {kind} ({basis})"

    def override_type(self, joint_type: str, release: MemberRelease):
        """Set the rule for a joint class, e.g. policy.override_type('TButtJoint', MemberRelease.rigid())."""
        self.by_type[joint_type] = release
        return self

    def override_instance(self, joint_guid: str, release: MemberRelease):
        """Set the rule for one specific joint, overriding its type rule."""
        self.by_instance[str(joint_guid)] = release
        return self


def policy_from_connector_mode(connector_mode: Optional[str]) -> JointPolicy:
    """Translate the legacy connector_mode string into a policy.

    Kept so existing callers ('rigid' / anything else) keep working while the
    richer policy is adopted.
    """
    if connector_mode == "rigid":
        return JointPolicy.rigid()
    return JointPolicy.conservative()
