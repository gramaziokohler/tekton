"""What OpenSees wants, in numbers - and how the neutral model's numbers become them.

OpenSees has no units and no axis convention of its own. The neutral model is
kN, m, kNm and Z-up, so almost everything goes in as it is. Three things do
not, and they all live here:

- **Stiffness.** The material presets carry E and G in MPa (N/mm²); OpenSees
  needs them in the model's force/length units, kN/m² - a factor of 1000.
- **Section constants.** OpenSees wants A, Iy, Iz and the torsion constant J
  on the element. The neutral section stores width and height only; J is
  derived here for rectangles (Roark's β·b³·h, β from the aspect ratio).
- **Local axes.** An element's local x runs from node i to node j. The
  neutral member stores its local **y** (the section width direction);
  OpenSees wants a vector in the local x-z plane, so it gets local z = x × y.
  Member loads are authored as global vectors and OpenSees applies them in
  local axes - projected here.

Signs: the neutral model's member convention is RFEM's (the Dlubal reader
passes it through). Calibrated on 2026-09-15 across the 200 beams of the
sticks model, midspan station against midspan station: OpenSees' section
moments My, Mz and axial force have RFEM's sign as they are; the shear
derived from the end forces has the opposite sign. Reactions: the neutral
model stores the force *on the structure* (OpenSees' ``nodeReaction``);
RFEM reports the force on the support, which the Dlubal reader negates.
See ``tests/unit/test_opensees_backend.py`` for the fixture that pins the
two backends against each other.
"""

from compas.geometry import Vector
from compas.geometry import cross_vectors
from compas.geometry import normalize_vector

#: MPa (N/mm²) -> kN/m².
MPA_TO_KN_M2 = 1000.0

#: Standard gravity, for self-weight from density (kg/m³ -> kN/m³).
G_ACC = 9.81

#: Signs of OpenSees' section forces relative to the neutral (RFEM) convention.
MY_SIGN = 1.0
MZ_SIGN = 1.0
#: The shear interpolated from the end forces comes out opposite to RFEM's.
SHEAR_SIGN = -1.0

#: Rigid links become very stiff beams (OpenSees' rigidLink loses the reactions,
#: see the spike). Stiffness factor relative to the model's own material.
RIGID_FACTOR = 1.0e4


def stiffness_kn_m2(mpa):
    """E or G from MPa into kN/m²."""
    return float(mpa) * MPA_TO_KN_M2


def rectangle_torsion_constant(b, h):
    """Torsion constant J of a solid rectangle (Roark), long side h, short side b.

    β(h/b) interpolated between the tabulated values; exact enough for a
    structural model whose torsion is a secondary effect.
    """
    b, h = float(b), float(h)
    if b <= 0 or h <= 0:
        return 0.0
    if b > h:
        b, h = h, b
    ratio = h / b
    table = [(1.0, 0.141), (1.5, 0.196), (2.0, 0.229), (2.5, 0.249), (3.0, 0.263), (4.0, 0.281), (5.0, 0.291), (10.0, 0.312)]
    if ratio >= table[-1][0]:
        beta = 0.333 - 0.21 / ratio  # thin-strip limit
    else:
        beta = table[0][1]
        for (r0, b0), (r1, b1) in zip(table, table[1:]):
            if r0 <= ratio <= r1:
                beta = b0 + (b1 - b0) * (ratio - r0) / (r1 - r0)
                break
    return beta * b ** 3 * h


def section_constants(width, height):
    """(A, Iy, Iz, J) of a rectangle with width along local y and height along local z.

    Iy bends about the local y axis (the strong axis when height > width),
    Iz about local z.
    """
    b, h = float(width), float(height)
    area = b * h
    iy = b * h ** 3 / 12.0
    iz = h * b ** 3 / 12.0
    return area, iy, iz, rectangle_torsion_constant(b, h)


def local_axes(start, end, orientation):
    """(x, y, z) unit vectors of a member: x along the axis, y the orientation, z = x × y.

    A degenerate orientation (parallel to the axis or zero) falls back to the
    global axis least aligned with x, so a vertical member still gets a frame.
    """
    x = normalize_vector([end[0] - start[0], end[1] - start[1], end[2] - start[2]])
    y = list(orientation) if orientation is not None else [0.0, 0.0, 1.0]
    dot = x[0] * y[0] + x[1] * y[1] + x[2] * y[2]
    y = [y[0] - x[0] * dot, y[1] - x[1] * dot, y[2] - x[2] * dot]
    if (y[0] ** 2 + y[1] ** 2 + y[2] ** 2) ** 0.5 < 1e-9:
        fallback = min(([1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]), key=lambda a: abs(a[0] * x[0] + a[1] * x[1] + a[2] * x[2]))
        dot = x[0] * fallback[0] + x[1] * fallback[1] + x[2] * fallback[2]
        y = [fallback[0] - x[0] * dot, fallback[1] - x[1] * dot, fallback[2] - x[2] * dot]
    y = normalize_vector(y)
    z = normalize_vector(cross_vectors(x, y))
    return Vector(*x), Vector(*y), Vector(*z)


def to_local(vector, axes):
    """Global vector -> (x, y, z) components along the member's local axes."""
    x, y, z = axes
    v = Vector(*vector)
    return v.dot(x), v.dot(y), v.dot(z)


__all__ = [
    "MPA_TO_KN_M2",
    "G_ACC",
    "MY_SIGN",
    "MZ_SIGN",
    "SHEAR_SIGN",
    "RIGID_FACTOR",
    "stiffness_kn_m2",
    "rectangle_torsion_constant",
    "section_constants",
    "local_axes",
    "to_local",
]
