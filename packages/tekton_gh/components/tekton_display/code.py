"""Tekton Display - the analysis model as a picture.

Elements as their sections, connections highlighted (rigid links dark,
couplings magenta, hinged ends as white spheres, shared nodes grey), supports
as the symbols engineers read at a glance - pyramid on a plate for pinned,
rollers under the plate along the free direction, a ball for a ball support,
a block for fixed - each with a label saying what is fixed. Loads as arrows
that scale with their value (point loads at nodes, member loads as a row of
arrows with a bar), moments as rings; support reactions in blue once the
model carries results.

Everything comes out as vertex-coloured meshes, so the picture is coloured
without a Custom Preview; labels are text dots, drawn only with `badges` on.
The beams themselves are drawn by the component (SDK mode,
`DrawViewportMeshes`) with `opacity`, so
the connections inside the timber stay visible; the `elements` output still
carries the solid meshes for anything downstream. What to draw and where is
decided in `tekton_gh.model_view` (pure, tested); this script only builds
Rhino geometry from those specs. `Tekton Inspect` is the bare debug view
(system lines, nodes, ticks); this is the one to show people.
"""
# venv: tekton-test
# r: compas, compas_timber

import math
import os
import sys

import Grasshopper
import Rhino
import System

ghenv.Component.Message = "Display"  # type: ignore # noqa: F821


def _repo_candidates(explicit):
    """Where to look for the monorepo, cheapest and most certain first.

    Only `isdir` calls - never a filesystem search, this runs on every solve.
    The document guess is what makes a definition stored inside the repo work
    with nothing configured at all; the cache file is what makes the path
    survive a Rhino restart. Mirrors tekton_gh.env.discover_repo_root, which
    cannot be imported yet - finding the repo is what makes it importable.
    """
    yield explicit
    yield os.environ.get("TEKTON_REPO")
    try:
        document = ghenv.Component.OnPingDocument()  # type: ignore # noqa: F821
        current = os.path.dirname(document.FilePath) if document and document.FilePath else None
        for _ in range(8):
            if not current:
                break
            yield current
            parent = os.path.dirname(current)
            current = None if parent == current else parent
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.expanduser("~"), ".tekton", "repo-root")) as handle:
            yield handle.read()
    except Exception:
        pass
    for guess in ("~/Documents/GitHub/tekton", "~/Documents/git/tekton", "~/git/tekton",
                  "~/GitHub/tekton", "~/Developer/tekton", "~/src/tekton", "~/tekton",
                  "~/Documents/tekton", "~/Desktop/tekton"):
        yield guess


def _remember_repo(root):
    """Write the root down so the next Rhino session finds it by itself."""
    try:
        directory = os.path.join(os.path.expanduser("~"), ".tekton")
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, "repo-root"), "w") as handle:
            handle.write(root)
    except Exception:
        pass


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and compas_timber_fea, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("compas_timber_fea") and importlib.util.find_spec("tekton_gh"):
            return None
    root = None
    for candidate in _repo_candidates(explicit_repo):
        candidate = str(candidate).strip() if candidate else ""
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
    _remember_repo(root)
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- COMPONENT (SDK mode) ---------------------
# Rhino 8 script components run a class deriving from GH_ScriptInstance
# when one is defined. Inputs arrive as RunScript arguments in parameter
# order; outputs are returned in output order. DrawViewportMeshes is the
# hook that the plain script mode does not have - it is what lets the
# beams be transparent.


class TektonDisplay(Grasshopper.Kernel.GH_ScriptInstance):
    def RunScript(self, structural, show, geometry, load_case, scale, load_scale, opacity, badges):
        elements = []
        members = []
        connections = []
        supports = []
        loads = []
        reactions = []
        labels = []
        legend = []
        self._solid = []
        self._material = None


        elements = []
        members = []
        connections = []
        supports = []
        loads = []
        reactions = []
        labels = []
        legend = []

        if structural is None:
            _warn("No StructuralModel connected.")
        else:
            _setup()
            import Rhino.Geometry as rg
            from System.Drawing import Color

            import importlib
            import tekton_gh.model_view
            import tekton_gh.visualize
            importlib.reload(tekton_gh.model_view)
            from tekton_gh.model_view import connection_specs, element_specs, legend as _legend, load_specs, reaction_specs, support_specs, surface_connection_specs, surface_specs
            from tekton_gh.rhino_io import member_lines
            from tekton_gh.visualize import section_mesh

            units = getattr(structural, "source_units", "m")
            factor = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(units, 1.0)
            size = (scale if scale else 0.15)  # symbol size, metres
            per_kn = (load_scale if load_scale else 0.25)  # arrow length per kN, metres
            case_id = int(load_case) if load_case else None

            def P(p):
                return rg.Point3d(p[0], p[1], p[2])

            def V(v):
                return rg.Vector3d(v[0], v[1], v[2])

            def painted(mesh, colour):
                mesh.VertexColors.Clear()
                c = Color.FromArgb(*colour)
                for _ in range(mesh.Vertices.Count):
                    mesh.VertexColors.Add(c)
                return mesh

            def frame(point, axis):
                plane = rg.Plane(P(point), V(axis))
                return plane

            def mesh_of(spec):
                kind = spec["kind"]
                colour = spec["colour"]
                if kind == "rod":
                    a, b = P(spec["start"]), P(spec["end"])
                    line = rg.Line(a, b)
                    if line.Length < 1e-9:
                        return None
                    cyl = rg.Cylinder(rg.Circle(rg.Plane(a, line.Direction), spec["radius"]), line.Length)
                    return painted(rg.Mesh.CreateFromCylinder(cyl, 1, 8), colour)
                if kind == "sphere":
                    return painted(rg.Mesh.CreateFromSphere(rg.Sphere(P(spec["point"]), spec["radius"]), 8, 6), colour)
                if kind == "pyramid":
                    # rg.Cone: the plane origin is the APEX, the base circle sits at
                    # `height` along the plane normal. Apex at the node, base below.
                    s = spec["size"]
                    cone = rg.Cone(rg.Plane(P(spec["apex"]), V(spec["axis"])), s, s * 0.6)
                    m = rg.Mesh.CreateFromCone(cone, 1, 4, True)
                    return painted(m, colour)
                if kind == "plate":
                    s, t = spec["size"], spec["thickness"]
                    plane = frame(spec["point"], spec["axis"])
                    box = rg.Box(plane, rg.Interval(-s / 2, s / 2), rg.Interval(-s / 2, s / 2), rg.Interval(0, t))
                    return painted(rg.Mesh.CreateFromBox(box, 1, 1, 1), colour)
                if kind == "box":
                    s = spec["size"]
                    plane = frame(spec["point"], spec["axis"])
                    box = rg.Box(plane, rg.Interval(-s / 2, s / 2), rg.Interval(-s / 2, s / 2), rg.Interval(-s / 2, s / 2))
                    return painted(rg.Mesh.CreateFromBox(box, 1, 1, 1), colour)
                if kind == "cylinder":
                    axis = V(spec["axis"])
                    centre = P(spec["point"]) - axis * (spec["length"] / 2)
                    cyl = rg.Cylinder(rg.Circle(rg.Plane(centre, axis), spec["radius"]), spec["length"])
                    return painted(rg.Mesh.CreateFromCylinder(cyl, 1, 10), colour)
                if kind == "arrow":
                    a, b = P(spec["start"]), P(spec["end"])
                    line = rg.Line(a, b)
                    if line.Length < 1e-9:
                        return None
                    head = min(line.Length * 0.3, size * factor * 0.5)
                    r = head * 0.35
                    shaft_len = max(line.Length - head, 1e-6)
                    shaft = rg.Mesh.CreateFromCylinder(rg.Cylinder(rg.Circle(rg.Plane(a, line.Direction), r * 0.3), shaft_len), 1, 6)
                    tip_plane = rg.Plane(b, -line.Direction)
                    cone = rg.Mesh.CreateFromCone(rg.Cone(tip_plane, head, r), 1, 8, True)
                    shaft.Append(cone)
                    return painted(shaft, colour)
                if kind == "arc":
                    plane = frame(spec["point"], spec["axis"])
                    ring = rg.Torus(plane, spec["radius"], spec["radius"] * 0.08)
                    m = rg.Mesh.CreateFromTorus(ring, 24, 6) if hasattr(rg.Mesh, "CreateFromTorus") else None
                    if m is None:
                        return None
                    return painted(m, colour)
                if kind == "slab":
                    # The mid-plane outline extruded by +-t/2 along its normal.
                    pts = [P(p) for p in spec["points"]]
                    n = len(pts)
                    normal = rg.Vector3d.CrossProduct(pts[1] - pts[0], pts[2] - pts[0])
                    if not normal.Unitize():
                        return None
                    half = normal * (spec["thickness"] / 2.0)
                    m = rg.Mesh()
                    for p in pts:
                        m.Vertices.Add(p - half)
                    for p in pts:
                        m.Vertices.Add(p + half)
                    for i in range(n):
                        j = (i + 1) % n
                        m.Faces.AddFace(i, j, n + j, n + i)
                    cap_faces = []
                    if n == 4:
                        cap_faces.append((m.Faces.AddFace(3, 2, 1, 0),
                                          m.Faces.AddFace(n, n + 1, n + 2, n + 3)))
                    else:
                        # Cap the two faces by triangulating the outline. A
                        # fan from corner 0 only works while the outline is
                        # convex; a faceted shell is full of plates that step
                        # inwards (38 of 46 on the hypar example), and there
                        # the fan spills straight across the notch.
                        cap = None
                        try:
                            boundary = rg.Polyline([p - half for p in pts] + [pts[0] - half])
                            cap = rg.Mesh.CreateFromClosedPolyline(boundary)
                        except Exception:
                            cap = None
                        if cap is not None and cap.Faces.Count:
                            # CreateFromClosedPolyline reorders its vertices,
                            # so map each one back onto ours by position.
                            index_of = {}
                            for c in range(cap.Vertices.Count):
                                cv = cap.Vertices[c]
                                best, best_d = 0, None
                                for i in range(n):
                                    d = (pts[i] - half).DistanceTo(rg.Point3d(cv.X, cv.Y, cv.Z))
                                    if best_d is None or d < best_d:
                                        best, best_d = i, d
                                index_of[c] = best
                            bottom, top = [], []
                            for c in range(cap.Faces.Count):
                                f = cap.Faces[c]
                                a, b2, c2 = index_of[f.A], index_of[f.B], index_of[f.C]
                                bottom.append(m.Faces.AddFace(a, c2, b2))
                                top.append(m.Faces.AddFace(n + a, n + b2, n + c2))
                            cap_faces.append((bottom, top))
                        else:
                            bottom, top = [], []
                            for i in range(1, n - 1):
                                bottom.append(m.Faces.AddFace(0, i + 1, i))
                                top.append(m.Faces.AddFace(n, n + i, n + i + 1))
                            cap_faces.append((bottom, top))
                    # An n-gon caps cannot be one mesh face, so each is a fan
                    # or a triangulation - and Rhino draws a wire along every
                    # one of those internal edges, which reads as if the
                    # plate were chopped up. Grouping them into an Ngon keeps
                    # the geometry and hides the internal wires: the plate is
                    # drawn as the one face it is.
                    try:
                        for bottom, top in cap_faces:
                            if isinstance(bottom, int):
                                continue  # a quad cap is already one face
                            if len(bottom) > 1:
                                m.Ngons.AddNgon(rg.MeshNgon.Create(
                                    list(range(n)), list(bottom)))
                            if len(top) > 1:
                                m.Ngons.AddNgon(rg.MeshNgon.Create(
                                    list(range(n, 2 * n)), list(top)))
                    except Exception:
                        pass
                    m.Normals.ComputeNormals()
                    return painted(m, colour)
                if kind == "beam":
                    vertices, faces, _c = section_mesh([spec["start"], spec["end"]], spec["width"], spec["height"], spec["orientation"])
                    m = rg.Mesh()
                    for x, y, z in vertices:
                        m.Vertices.Add(x, y, z)
                    for f in faces:
                        m.Faces.AddFace(f[0], f[1], f[2], f[3])
                    m.Normals.ComputeNormals()
                    return painted(m, colour)
                return None

            def build(specs, target):
                for spec in specs:
                    if spec["kind"] == "text":
                        labels.append(rg.TextDot(spec["text"], P(spec["point"])))
                        continue
                    m = mesh_of(spec)
                    if m is not None:
                        target.append(m)
                    if spec.get("label") and spec["kind"] in ("arrow", "arc"):
                        anchor = spec.get("start", spec.get("point"))
                        labels.append(rg.TextDot(spec["label"], P(anchor)))

            ALL = {"members", "connections", "supports", "loads", "reactions"}
            wanted = set(str(s).lower().strip('"') for s in (show or [])) & ALL
            if show and not wanted:
                _warn("'show' has no known entry ({}) - showing everything. Allowed: {}.".format(", ".join(str(s) for s in show), ", ".join(sorted(ALL))))
            wanted = wanted or ALL
            # The member geometry (beam sections, plate slabs) is its own
            # toggle, off by default: it is drawn semi-transparent by
            # DrawViewportMeshes, but still clutters the wire model.
            if geometry:
                wanted.add("elements")
            if "members" in wanted:
                members = member_lines(structural, scale=factor)
            if "elements" in wanted:
                build(element_specs(structural, scale=factor), elements)
                build(surface_specs(structural, scale=factor), elements)
            if "connections" in wanted:
                build(connection_specs(structural, scale=factor, size=size), connections)
                build(surface_connection_specs(structural, scale=factor, size=size), connections)
            if "supports" in wanted:
                build(support_specs(structural, scale=factor, size=size), supports)
            if "loads" in wanted:
                build(load_specs(structural, load_case_id=case_id, scale=factor, size=size, per_kn=per_kn), loads)
            if "reactions" in wanted:
                build(reaction_specs(structural, load_case_id=case_id, scale=factor, size=size, per_kn=per_kn), reactions)

            legend = _legend(structural, load_case_id=case_id)
            legend.append("Symbol size {} m, arrows {} m per kN".format(size, per_kn))
            if "reactions" in wanted and not (getattr(structural, "results", None) or {}):
                legend.append("No results yet - reactions appear after Tekton Run.")


        for line in legend:
            print(line)

        # The text dots - support types, load values - are off unless asked
        # for: on a real model there are hundreds, and they bury the picture.
        if not badges:
            labels = []

        # The beams: drawn here, not by Grasshopper - see DrawViewportMeshes.
        alpha = 0.35 if opacity is None else max(0.0, min(1.0, float(opacity)))
        try:
            from System.Drawing import Color as _Color

            self._solid = list(elements)
            self._material = Rhino.Display.DisplayMaterial(_Color.FromArgb(214, 186, 132), 1.0 - alpha)
            # Keep the default (opaque) preview of the elements output off.
            ghenv.Component.Params.Output[0].Hidden = True  # type: ignore # noqa: F821
        except Exception:
            self._solid = []

        return elements, members, connections, supports, loads, reactions, labels, legend

    def DrawViewportMeshes(self, args):
        # Runs on every redraw; nothing may escape here.
        try:
            material = self._material
            for mesh in self._solid or []:
                args.Display.DrawMeshShaded(mesh, material)
        except Exception:
            pass

    def DrawViewportWires(self, args):
        try:
            for mesh in self._solid or []:
                args.Display.DrawMeshWires(mesh, System.Drawing.Color.FromArgb(120, 95, 60), 1)
        except Exception:
            pass
