"""Hypar Shell - a faceted hypar as a connected TimberModel of plates.

The script body of the "Hypar Shell" component in
tekton_plates_opensees_hypar.ghx, kept here so it is versioned and readable;
the .ghx carries a copy.

Input is a tessellated hyperbolic paraboloid: a list of planar trimmed
surfaces, one per facet, that already share their edges exactly. Each facet
becomes one `Plate`; the shell stays one piece because neighbouring plates end
up on the *same* nodes.

Two things about the geometry are not cosmetic:

- **The outline is shifted by -t/2 along the facet normal.**
  `Plate.from_outline_thickness` extrudes to one side: the polyline it is
  given becomes `outline_a`, a *face* of the panel, and the mid-plane lands
  t/2 away along that plate's own normal. The analysis model is built from
  mid-planes, so with the raw outline every facet's mid-plane drifts off in a
  different direction (each facet has a different normal) and two neighbours
  no longer meet: 46 facets translate into 46 loose pieces, 250 nodes, none
  shared. Pre-shifting the outline by -t/2 puts the mid-plane back onto the
  original surface, where the facets do share edges - 118 nodes, 66 of them
  shared by three plates, one connected component.
- **No plate joints are created.** `PlateMiterJoint` and friends exist to give
  an edge a *release* (a hinge, a spring). Two plates that share their nodes
  are already rigidly continuous, which is what a monolithic shell wants.
  Creating joints anyway would not help: once the outlines are shifted onto
  the mid-plane the facets no longer touch face-to-face, so
  `PlateConnectionSolver` reports TOPO_UNKNOWN and every joint is rejected.

Supports are chosen per shell and returned as points, for Tekton Support
Nodes to snap onto - see `supports` below. They are the *facet corners* of
the descending edges; the analysis model has more nodes along those edges
than that, and supporting all of them (a true line support) is both stiffer
and better conditioned. `TektonSupportNodes` snaps per point, so feed it
these and raise its tolerance, or select by level, when a line support is
what the structure really has. Dimensions in document units (the document
is in metres).
"""
# venv: tekton-test
# r: compas, compas_timber

import Grasshopper
import Rhino.Geometry as rg


class Script_Instance(Grasshopper.Kernel.GH_ScriptInstance):
    def RunScript(self, surfaces, thickness, support_mode, tolerance):
        from compas.geometry import Point, Polyline, Vector
        from compas_timber.elements import Plate
        from compas_timber.model import TimberModel

        T = float(thickness or 0.2)
        tol = float(tolerance or 0.01)
        mode = (support_mode or "low_edges").strip().lower()

        info = []
        if not surfaces:
            return None, [], [], ["no surfaces connected"]

        # --- one planar facet -> one outline, plus the facet's own normal ---
        facets = []
        skipped = 0
        for surface in surfaces:
            brep = surface if isinstance(surface, rg.Brep) else rg.Brep.CreateFromSurface(surface)
            if brep is None:
                skipped += 1
                continue
            # The outer boundary as a single closed polyline. A facet is
            # planar and untrimmed on the inside, so the naked edges join
            # into exactly one curve; anything else is not a facet.
            joined = rg.Curve.JoinCurves(brep.DuplicateNakedEdgeCurves(True, False), tol)
            if len(joined) != 1:
                skipped += 1
                continue
            curve = joined[0]
            got_polyline, polyline = curve.TryGetPolyline()
            got_plane, plane = curve.TryGetPlane(tol)
            if not got_polyline or not got_plane:
                skipped += 1
                continue
            points = [(p.X, p.Y, p.Z) for p in polyline]
            if points[0] != points[-1]:
                points.append(points[0])
            normal = (plane.Normal.X, plane.Normal.Y, plane.Normal.Z)
            facets.append((points, normal))

        if skipped:
            info.append("{} input surface(s) were not planar single-loop facets - skipped".format(skipped))

        # --- plates, each shifted so its MID-plane is the original facet ---
        model = TimberModel()
        plates = []
        for points, normal in facets:
            shifted = Polyline([
                Point(x - normal[0] * T / 2.0, y - normal[1] * T / 2.0, z - normal[2] * T / 2.0)
                for (x, y, z) in points
            ])
            plate = Plate.from_outline_thickness(shifted, T, vector=Vector(*normal))
            plates.append(plate)
            model.add_element(plate)

        # --- how well the tessellation is stitched, for the report ---
        # Quantised so that two corners that are "the same point" compare
        # equal; the analysis model merges nodes on the same tolerance.
        def node_key(point, quantum=0.02):
            return (round(point[0] / quantum), round(point[1] / quantum), round(point[2] / quantum))

        edge_owners = {}
        boundary_vertices = {}
        for facet_index, (points, _) in enumerate(facets):
            corners = points[:-1]
            count = len(corners)
            for index in range(count):
                a, b = corners[index], corners[(index + 1) % count]
                ka, kb = node_key(a), node_key(b)
                boundary_vertices[ka] = a
                boundary_vertices[kb] = b
                # The owner is the facet, not the corner: an edge is "shared"
                # when two different facets claim it.
                edge_owners.setdefault(tuple(sorted([ka, kb])), []).append(facet_index)
        shared = sum(1 for owners in edge_owners.values() if len(owners) > 1)
        naked = [edge for edge, owners in edge_owners.items() if len(owners) == 1]
        info.append("{} plates, t = {} - {} shared edges, {} naked".format(
            len(plates), T, shared, len(naked)))
        if shared == 0 and len(plates) > 1:
            info.append("WARNING: no shared edges - the facets do not touch, the shell will be loose pieces")

        # --- support points on the naked boundary ---
        # Chosen per *edge*, not per vertex. On a saddle the boundary is two
        # edges that descend and two that rise, and they meet at the corners:
        # a vertex rule either takes the shared corners twice or, at a tight
        # threshold, collapses to the two lowest corners alone - and two
        # pinned points let the shell rotate about the line through them
        # (measured: 34 km of "deflection"). An edge counts as descending when
        # BOTH its ends are low; see the `low_edges` branch for why the
        # midpoint is not enough.
        naked_points = {}
        for a, b in naked:
            naked_points[a] = boundary_vertices[a]
            naked_points[b] = boundary_vertices[b]
        candidates = list(naked_points.values())

        supports = []
        if candidates:
            zs = [p[2] for p in candidates]
            z_low, z_high = min(zs), max(zs)
            span = z_high - z_low

            if mode == "all_edges":
                chosen = candidates
                info.append("supports: the whole naked boundary")
            elif mode == "lowest":
                chosen = [p for p in candidates if p[2] <= z_low + tol]
                info.append("supports: the lowest boundary points only (z = {:.3f})".format(z_low))
            else:  # low_edges
                # BOTH ends of the edge have to be low, not just its midpoint.
                # A hypar's corners are often chamfered: a short edge runs
                # from the low edge up to the corner. Its *midpoint* still
                # falls below half height, so a midpoint test drags a handful
                # of stray corner supports into the model, scattered and -
                # when the shell is only 180-degree rotationally symmetric,
                # as a hypar off a real surface usually is - not mirrored
                # either. The deflection then comes out lopsided: 0.33 mm
                # against 0.73 mm on two geometrically identical plates.
                cut = z_low + 0.5 * span
                keys = {}
                for a, b in naked:
                    pa, pb = boundary_vertices[a], boundary_vertices[b]
                    if pa[2] <= cut and pb[2] <= cut:
                        keys[a] = pa
                        keys[b] = pb
                # The analysis model puts a node only at a facet corner, so
                # the corners of these edges are all there is to support -
                # and here they sit on one straight line each, which lets the
                # shell rock about that line (measured: a mechanism, 4e9 mm).
                # What gives the support its width is the row of corners just
                # inboard of the edge, so those come along. The band has to
                # stay narrow: taking every corner below half height reaches
                # a quarter of the way into the span and props up half the
                # structure. One facet deep is enough to stop the rocking.
                keep = dict(keys)
                edge_pts = list(keys.values())
                if edge_pts:
                    reach = 0.0
                    for a, b in naked:
                        if a in keys and b in keys:
                            pa, pb = boundary_vertices[a], boundary_vertices[b]
                            reach = max(reach, sum((pb[i] - pa[i]) ** 2 for i in range(3)) ** 0.5)
                    reach = reach or span * 0.1
                    for key_, point in boundary_vertices.items():
                        if point[2] > cut:
                            continue
                        near = min(sum((point[i] - e[i]) ** 2 for i in range(3)) ** 0.5
                                   for e in edge_pts)
                        if near <= reach:
                            keep[key_] = point
                chosen = list(keep.values())
                info.append("supports: the descending edges plus one facet inboard (z <= {:.3f})".format(cut))

            supports = [rg.Point3d(*p) for p in chosen]
            info.append("{} support point(s) of {} boundary points".format(
                len(supports), len(candidates)))
            if len(supports) < 3:
                info.append("WARNING: fewer than 3 support points - the shell is a mechanism")

        # --- preview: the facets themselves ---
        preview = []
        for surface in surfaces:
            brep = surface if isinstance(surface, rg.Brep) else rg.Brep.CreateFromSurface(surface)
            if brep is not None:
                preview.append(brep)

        return model, supports, preview, info
