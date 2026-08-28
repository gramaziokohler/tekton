"""Dlubal-specific coordinate conventions.

RFEM/RSTAB use a global Z axis pointing down, whereas COMPAS (and the neutral
StructuralModel) are Z-up. Everything that depends on that difference belongs
here, at the backend boundary, so the neutral layer stays convention-free.
"""

import math

from compas.geometry import Vector


def vector_from_dlubal(x, y, z):
    """Convert a global vector from Dlubal's Z-down space to the neutral Z-up space.

    The inverse of the Z negation applied when pushing geometry; used for
    result quantities expressed in global coordinates (displacements,
    reactions).
    """
    return Vector(x, y, -z)


def calculate_beta_from_vector(node_start_point, node_end_point, orientation_vector):
    """Convert an agnostic orientation vector into Dlubal's beta rotation angle.

    The neutral model stores the member's local y axis as a vector in COMPAS
    (Z-up) space. Dlubal instead expects a rotation angle measured against its
    own default orientation in Z-down space, so both the member axis and the
    target vector are mirrored before the angle is computed.
    """
    # 1. Member axis in Dlubal space (Z inverted relative to COMPAS)
    x_D = Vector(
        node_end_point.x - node_start_point.x,
        node_end_point.y - node_start_point.y,
        -(node_end_point.z - node_start_point.z)
    )
    if x_D.length < 1e-9:
        return 0.0
    x_D.unitize()

    # 2. Target y vector in Dlubal space
    y_target = Vector(orientation_vector.x, orientation_vector.y, -orientation_vector.z)
    if y_target.length < 1e-9:
        return 0.0
    y_target.unitize()

    global_z_dlubal = Vector(0, 0, 1)
    if abs(x_D[2]) > 0.999:  # near vertical
        y_default = Vector(0, 1, 0)
    else:
        try:
            y_default = global_z_dlubal.cross(x_D)
            if y_default.length < 1e-9:
                y_default = Vector(0, 1, 0)
            else:
                y_default.unitize()
        except ZeroDivisionError:
            y_default = Vector(0, 1, 0)

    dot = max(-1.0, min(1.0, y_default.dot(y_target)))
    det = x_D.dot(y_default.cross(y_target))

    return math.atan2(det, dot)
