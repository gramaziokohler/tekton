"""Mechanical end conditions of a member.

A timber joint is a physical thing; a structural model needs its mechanical
idealisation. This module holds that idealisation in a backend-neutral form:
per degree of freedom, an end is either rigid, free, or a spring of a given
stiffness. Backends translate this into their own vocabulary (RFEM member
hinges, SAF hinge relations).
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from compas.geometry import Vector

RIGID = float("inf")
FREE = 0.0

#: Order used whenever the six degrees of freedom are addressed positionally.
DOFS = ("ux", "uy", "uz", "rx", "ry", "rz")


@dataclass
class MemberRelease:
    """Stiffness per degree of freedom at one end of a member.

    Values follow the same convention as :class:`StructuralSupport`:
    ``inf`` is fully restrained (continuous), ``0.0`` is fully released, and any
    finite value is a spring stiffness (kN/m for translations, kNm/rad for
    rotations) in the member's local coordinate system.
    """

    ux: float = RIGID
    uy: float = RIGID
    uz: float = RIGID
    rx: float = RIGID
    ry: float = RIGID
    rz: float = RIGID
    name: Optional[str] = None

    @classmethod
    def rigid(cls, name="rigid"):
        """A fully continuous connection: nothing is released."""
        return cls(name=name)

    @classmethod
    def pinned(cls, name="pinned"):
        """A hinge: translations continuous, bending released, torsion kept.

        This is the conservative default for timber connections, which rarely
        transfer meaningful bending moments.
        """
        return cls(ry=FREE, rz=FREE, name=name)

    @classmethod
    def spherical(cls, name="spherical"):
        """All three rotations released, translations continuous."""
        return cls(rx=FREE, ry=FREE, rz=FREE, name=name)

    @classmethod
    def hinged_edge(cls, name="hinged edge"):
        """A line hinge along a plate edge: bending about the edge is released.

        Along an edge only rotation about the edge axis (local x) is meaningful,
        so this is the plate counterpart of :meth:`pinned`.
        """
        return cls(rx=FREE, name=name)

    def is_rigid(self):
        return all(getattr(self, dof) == RIGID for dof in DOFS)

    def released_dofs(self):
        """Names of the degrees of freedom that are not fully restrained."""
        return tuple(dof for dof in DOFS if getattr(self, dof) != RIGID)


@dataclass
class MemberEccentricity:
    """Offset of the member axis from the system line, in the member's local axes.

    Timber members frequently connect face to face rather than axis to axis;
    the offset carries that geometry without moving the system line.
    """

    start: Optional[Vector] = None
    end: Optional[Vector] = None

    def is_zero(self):
        return self.start is None and self.end is None


@dataclass
class LoadCombination:
    """A factored combination of load cases.

    ``factors`` maps a load case id to its partial safety / combination factor.
    """

    id: int
    name: str
    factors: dict = field(default_factory=dict)
    combination_type: str = "ULS"  # "ULS", "SLS", "CHARACTERISTIC", ...
