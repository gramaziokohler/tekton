"""The Dlubal coordinate conversion must be a rotation, never a reflection.

The plain Z negation used previously was a reflection (determinant -1):
asymmetric models arrived in RFEM/RSTAB as mirror images - observed live, not
hypothetical. These tests pin the fix.
"""

import pytest
from compas.geometry import Point
from compas.geometry import Vector

from compas_dlubal.dlubal.conventions import calculate_beta_from_vector
from compas_dlubal.dlubal.conventions import point_to_dlubal
from compas_dlubal.dlubal.conventions import vector_from_dlubal
from compas_dlubal.dlubal.conventions import vector_to_dlubal


def _triple_product(a, b, c):
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def test_conversion_preserves_handedness():
    """A right-handed frame must stay right-handed - this is the mirror test."""
    basis = (Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1))
    converted = [vector_to_dlubal(v) for v in basis]

    before = _triple_product(*basis)
    after = _triple_product(*converted)

    assert before > 0
    assert after > 0, "conversion flips handedness: models arrive mirrored"


def test_conversion_keeps_elevation_upright():
    """A point 3 m above ground must land at -3 in Dlubal's Z-down world."""
    x, y, z = point_to_dlubal(Point(1.0, 2.0, 3.0))

    assert z == -3.0
    assert x == 1.0


def test_conversion_is_an_involution():
    """Applying the map twice must return the original vector."""
    vector = Vector(1.2, -3.4, 5.6)

    converted = vector_to_dlubal(vector)
    back = vector_from_dlubal(converted.x, converted.y, converted.z)

    assert list(back) == pytest.approx(list(vector))


def test_a_chiral_point_set_stays_chiral():
    """Three points spanning a signed area with a height offset: an L-shape.

    Under a reflection the signed volume of the tetrahedron they form with the
    origin flips sign; under the rotation it must not.
    """
    points = (Point(1, 0, 0), Point(0, 2, 0), Point(0, 0, 3))
    converted = [point_to_dlubal(p) for p in points]

    before = _triple_product(*[tuple(p) for p in points])
    after = _triple_product(*converted)

    assert before * after > 0, "signed volume flipped: the model is mirrored"


def test_beta_for_default_orientation_is_zero():
    """A horizontal member whose y axis matches Dlubal's default needs no rotation."""
    start, end = Point(0, 0, 0), Point(4, 0, 0)
    # Dlubal default y for a horizontal x-member is global_z x member_axis.
    # In neutral space that corresponds to -Y for a member along +X.
    beta = calculate_beta_from_vector(start, end, Vector(0, -1, 0))

    assert beta == pytest.approx(0.0, abs=1e-9)
