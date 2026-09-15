"""Plate Box - a CLT slab on two shear walls, as a TimberModel from sliders.

The script body of the "Plate Box" component in tekton_test_plates.ghx, kept
here so it is versioned and readable; the .ghx carries a copy. Two wall
panels (at x = 0 and x = width) carrying a slab that spans between them -
a one-way slab, the simplest plate structure that makes sense. Everything on
centre-line dimensions (see build_plate_model.py for why that is not
cosmetic): the slab's mid-plane contains the wall tops, so the graph merges
the nodes and the slab is connected. Dimensions in document units.
"""
# venv: tekton-test
# r: compas, compas_timber

import Grasshopper
import Rhino.Geometry as rg


class Script_Instance(Grasshopper.Kernel.GH_ScriptInstance):
    def RunScript(self, width, depth, height, t_wall, t_slab):
        from compas.geometry import Point, Polyline, Vector
        from compas_timber.elements import Plate
        from compas_timber.model import TimberModel

        W = float(width or 4.0)
        D = float(depth or 3.0)
        H = float(height or 2.8)
        TW = float(t_wall or 0.1)
        TS = float(t_slab or 0.18)

        def rect(points):
            pts = [Point(*p) for p in points]
            return Polyline(pts + [pts[0]])

        model = TimberModel()
        # Outlines run counter-clockwise seen from outside; the extrusion
        # vector points inwards, so the mid-plane lands on the axis.
        walls = [
            Plate.from_outline_thickness(rect([(W, 0, 0), (W, D, 0), (W, D, H), (W, 0, H)]), TW, vector=Vector(-1, 0, 0)),
            Plate.from_outline_thickness(rect([(0, D, 0), (0, 0, 0), (0, 0, H), (0, D, H)]), TW, vector=Vector(1, 0, 0)),
        ]
        # The slab on centre-line dimensions too: its mid-plane must contain
        # the walls' top edges, which sit at z = H, inset by half a wall
        # thickness in x. So the outline starts half a slab below H and is
        # inset by TW/2 at the walls - otherwise the slab floats above the
        # walls and the analysis model falls apart into two pieces.
        h = TW / 2.0
        z0 = H - TS / 2.0
        slab = Plate.from_outline_thickness(rect([(h, 0, z0), (W - h, 0, z0), (W - h, D, z0), (h, D, z0)]), TS, vector=Vector(0, 0, 1))
        for element in walls + [slab]:
            model.add_element(element)
        # No plate joints: the two walls do not meet, and wall-to-slab is a
        # shared-node connection in the analysis model (rigid line).

        # Wall feet as support points (the translator reads these off beams
        # only today; Tekton Support Nodes with level 0 is what actually
        # supports the analysis model - the attribute documents the intent).
        walls[0].attributes["support_points"] = [[W, 0.0, 0.0], [W, D, 0.0]]
        walls[1].attributes["support_points"] = [[0.0, D, 0.0], [0.0, 0.0, 0.0]]

        # Preview: the panels as boxes (everything is axis-aligned here).
        def box(x0, y0, z0, x1, y1, z1):
            return rg.Brep.CreateFromBox(rg.BoundingBox(rg.Point3d(x0, y0, z0), rg.Point3d(x1, y1, z1)))

        breps = [
            box(W - TW, 0, 0, W, D, H),
            box(0, 0, 0, TW, D, H),
            box(h, 0, z0, W - h, D, z0 + TS),
        ]
        info = [
            "{} plates ({} walls t={} + slab t={})".format(len(walls) + 1, len(walls), TW, TS),
            "slab {} x {} spanning {} m in x on two walls of height {}, centre-line dimensions".format(W, D, W - TW, H),
            "slab mid-plane at z = {} meets the wall tops: shared nodes, one connected model".format(H),
        ]
        return model, breps, info
