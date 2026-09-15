"""Build a plate model that makes structural sense.

Four CLT wall panels forming a closed box, plus a floor slab on top. The
simplest case that exercises the whole plate path: shear walls that carry the
slab down to the supports, and eight vertical edges where the idealisation has
to decide how stiff the connections are.

Two things about the geometry are not cosmetic:

- **Everything sits on centre-line dimensions.** The idealisation works with
  mid-planes, and a connection is only found where one plate's edge lies *in*
  the neighbouring plate's mid-plane. A model that merely looks right - walls
  standing under a slab - produces no coupling at all, and the analysis model
  falls apart into loose pieces.
- **The slab sits on centre-line dimensions too.** Its mid-plane must contain
  the walls' top edges (z = HEIGHT, inset by half a wall thickness), so its
  outline starts half a slab thickness below HEIGHT and is inset by T_WALL/2.
  With the slab merely "on top" its mid-plane floats 9 cm above the walls,
  the graph finds no shared nodes, and the analysis model is two pieces.

Dimensions in mm, matching the Rhino convention.
"""
import sys

from compas.data import json_dump
from compas.geometry import Point, Polyline, Vector
from compas_timber.connections import PlateLButtJoint
from compas_timber.elements import Plate
from compas_timber.model import TimberModel

WIDTH = 4000.0     # box, x
DEPTH = 3000.0     # box, y
HEIGHT = 2800.0    # top of walls = mid-plane of the slab
T_WALL = 100.0     # CLT 100
T_SLAB = 180.0     # CLT 180

# KNOWN_ISSUE (compas_timber, structural.py): the mid-surface frame is built as
# Frame(origin, direction, normal), which puts the plate normal into the frame's
# y-axis - so `frame.normal` ends up lying *in* the plate plane. The connection
# finder projects onto that normal, so it only finds edges between plates whose
# (wrong) normals happen to align: wall-to-wall works, wall-to-slab does not.
# The slab is therefore in the model as a load-bearing surface, but its edge
# coupling has to be added on the analysis side until this is fixed upstream.


def rect(points):
    """Closed polyline from corner points."""
    pts = [Point(*p) for p in points]
    return Polyline(pts + [pts[0]])


def build():
    model = TimberModel()

    # Four walls, each in its own plane, corners on centre-line dimensions.
    # The outline order runs counter-clockwise seen from outside, and the
    # extrusion vector points inwards, so the mid-plane lands on the axis.
    walls = [
        Plate.from_outline_thickness(
            rect([(0, 0, 0), (WIDTH, 0, 0), (WIDTH, 0, HEIGHT), (0, 0, HEIGHT)]),
            T_WALL, vector=Vector(0, 1, 0)),
        Plate.from_outline_thickness(
            rect([(WIDTH, 0, 0), (WIDTH, DEPTH, 0), (WIDTH, DEPTH, HEIGHT), (WIDTH, 0, HEIGHT)]),
            T_WALL, vector=Vector(-1, 0, 0)),
        Plate.from_outline_thickness(
            rect([(WIDTH, DEPTH, 0), (0, DEPTH, 0), (0, DEPTH, HEIGHT), (WIDTH, DEPTH, HEIGHT)]),
            T_WALL, vector=Vector(0, -1, 0)),
        Plate.from_outline_thickness(
            rect([(0, DEPTH, 0), (0, 0, 0), (0, 0, HEIGHT), (0, DEPTH, HEIGHT)]),
            T_WALL, vector=Vector(1, 0, 0)),
    ]

    h = T_WALL / 2.0
    z0 = HEIGHT - T_SLAB / 2.0
    slab = Plate.from_outline_thickness(
        rect([(h, h, z0), (WIDTH - h, h, z0), (WIDTH - h, DEPTH - h, z0), (h, DEPTH - h, z0)]),
        T_SLAB, vector=Vector(0, 0, 1))

    for element in walls + [slab]:
        model.add_element(element)

    # The four vertical corners. These are what holds the box together.
    for i in range(4):
        PlateLButtJoint.create(model, walls[i], walls[(i + 1) % 4])

    # Supports at the wall feet: every wall corner on the ground.
    corners = [(0.0, 0.0), (WIDTH, 0.0), (WIDTH, DEPTH), (0.0, DEPTH)]
    for i, wall in enumerate(walls):
        x0, y0 = corners[i]
        x1, y1 = corners[(i + 1) % 4]
        wall.attributes["support_points"] = [[x0, y0, 0.0], [x1, y1, 0.0]]

    return model


if __name__ == "__main__":
    model = build()
    print("plates:", len(list(model.plates)))
    print("joints:", [type(j).__name__ for j in model.joints])
    for plate in model.plates:
        pts = list(plate.outline_a.points)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
        print("  t=%-5.0f x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f]" % (
            plate.thickness, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/plates.json"
    json_dump(model, out)
    print("written:", out)
