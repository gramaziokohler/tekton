"""EC5 design checks computed in the neutral layer.

Tekton reads utilisation from RFEM's design add-on where one is available
(WP1); this package computes the same number itself, from the section forces
and the material (WP1b). Not as a replacement - as the path that also works
for the OpenSees backend, offline, in CI, and as a second opinion against
which a certified result can be compared.

What is *not* here: buckling and lateral-torsional buckling. They need a
buckling length, and the neutral model does not carry one. Every report
states that they were not verified; an unverified check must never look like a passed one.

Clause numbers refer to EN 1995-1-1 (Eurocode 5). Each table below names
the clause its values came from.
"""

from .factors import DesignAssumptions
from .factors import GAMMA_M_GLULAM
from .factors import GAMMA_M_SOLID
from .factors import LOAD_DURATION_CLASSES
from .factors import SERVICE_CLASSES
from .factors import gamma_M_for
from .factors import k_h_bending
from .factors import k_mod
from .sections import member_length
from .sections import section_properties
from .checks import CheckResult
from .checks import MemberCheck
from .checks import check_member
from .checks import check_model

__all__ = [
    "DesignAssumptions",
    "GAMMA_M_GLULAM",
    "GAMMA_M_SOLID",
    "LOAD_DURATION_CLASSES",
    "SERVICE_CLASSES",
    "gamma_M_for",
    "k_h_bending",
    "k_mod",
    "member_length",
    "section_properties",
    "CheckResult",
    "MemberCheck",
    "check_member",
    "check_model",
]
