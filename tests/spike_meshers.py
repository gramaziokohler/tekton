"""Spike: which mesher can give OpenSees conforming plate edges (2026-09-16).

Run with a venv that has compas_cgal, gmsh and libigl - NOT the repo venv;
this is a decision record, not a dependency. Findings are written up in
`docs/discussion/opensees-backend.md` under "Meshing for plates".

Result: gmsh, because `setTransfiniteCurve` lets a shared edge's node count be
prescribed. compas_cgal refines the boundary on its own and therefore cannot
guarantee that two plates meet on the same nodes.
"""
import numpy as np

# 4x3 plate, boundary deliberately pre-split: extra vertices on the bottom edge,
# as a shared BorderChain with a neighbour would produce.
BOUNDARY = [
    (0,0,0), (1,0,0), (2,0,0), (3,0,0), (4,0,0),
    (4,3,0), (0,3,0),
]
HOLE = [(1.5,1.0,0),(2.5,1.0,0),(2.5,2.0,0),(1.5,2.0,0)]

def check(name, verts, faces, expect_hole=True):
    verts = np.asarray(verts); faces = np.asarray(faces)
    kept = 0
    for b in BOUNDARY:
        d = np.linalg.norm(verts[:, :2] - np.array(b[:2]), axis=1)
        if d.min() < 1e-9: kept += 1
    # centroid of the hole must not be covered by any triangle
    hole_c = np.array([2.0, 1.5])
    covered = False
    for f in faces:
        p = verts[f][:, :2]
        d = np.array([p[1]-p[0], p[2]-p[0]]).T
        try: uv = np.linalg.solve(d, hole_c - p[0])
        except np.linalg.LinAlgError: continue
        if uv[0] >= -1e-9 and uv[1] >= -1e-9 and uv.sum() <= 1+1e-9:
            covered = True; break
    print(f"{name:28} verts={len(verts):4}  tris={len(faces):4}  "
          f"boundary kept {kept}/{len(BOUNDARY)}  hole {'MISSING' if covered else 'ok'}")

# --- CGAL ---
try:
    from compas_cgal.triangulation import constrained_delaunay_triangulation as cdt
    from compas.geometry import Point
    V, F = cdt([Point(*p) for p in BOUNDARY], holes=[[Point(*p) for p in HOLE]])
    check("CGAL cdt", V, F)
except Exception as e:
    print("CGAL cdt FAILED:", type(e).__name__, str(e)[:110])

try:
    from compas_cgal.triangulation import refined_delaunay_mesh as rdm
    from compas.geometry import Point
    V, F = rdm([Point(*p) for p in BOUNDARY], holes=[[Point(*p) for p in HOLE]], maxlength=0.5)
    check("CGAL refined (0.5 m)", V, F)
except Exception as e:
    print("CGAL refined FAILED:", type(e).__name__, str(e)[:110])

# --- gmsh ---
try:
    import gmsh
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("plate")
    def loop(pts, size):
        tags=[gmsh.model.geo.addPoint(x,y,z,size) for x,y,z in pts]
        lines=[gmsh.model.geo.addLine(tags[i], tags[(i+1)%len(tags)]) for i in range(len(tags))]
        return gmsh.model.geo.addCurveLoop(lines)
    o=loop(BOUNDARY,0.5); h=loop(HOLE,0.5)
    gmsh.model.geo.addPlaneSurface([o,h]); gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate(2)
    nt,nc,_=gmsh.model.mesh.getNodes(); V=np.array(nc).reshape(-1,3)
    et,en=gmsh.model.mesh.getElementsByType(2)
    idx={t:i for i,t in enumerate(nt)}
    F=np.array([[idx[n] for n in en[i*3:(i+1)*3]] for i in range(len(et))])
    check("gmsh (0.5 m)", V, F)
    gmsh.finalize()
except Exception as e:
    print("gmsh FAILED:", type(e).__name__, str(e)[:110])

# --- libigl: what does it actually offer? ---
try:
    import igl
    has = [n for n in ("triangulate","delaunay_triangulation") if hasattr(igl,n)]
    print(f"{'libigl':28} 2D meshers exposed: {has or 'NONE (it is a processing lib, not a mesher)'}")
except Exception as e:
    print("libigl FAILED:", e)


# ---------------------------------------------------------------- conformity
# The property that actually decides the library: two plates sharing an edge
# must end up with IDENTICAL nodes on it, or the OpenSees model has a crack.

def cgal_shared_edge(maxlength):
    """Mesh two neighbouring plates separately; compare the shared edge."""
    from compas_cgal.triangulation import refined_delaunay_mesh as rdm
    from compas.geometry import Point
    A = [(0,0,0),(4,0,0),(4,1.0,0),(4,2.0,0),(4,3,0),(0,3,0)]
    B = [(4,0,0),(8,0,0),(8,3,0),(4,3,0),(4,2.0,0),(4,1.0,0)]
    out = []
    for poly in (A, B):
        V, _ = rdm([Point(*p) for p in poly], maxlength=maxlength)
        V = np.asarray(V)
        out.append(np.array(sorted(V[np.abs(V[:, 0] - 4) < 1e-7][:, 1].round(6).tolist())))
    return out


def gmsh_shared_edge(size):
    """Same, but with the shared edge's node count prescribed."""
    import gmsh
    n = int(np.ceil(3.0 / size)) + 1

    def plate(x0, x1):
        gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("p"); g = gmsh.model.geo
        pts = [g.addPoint(x0,0,0,size), g.addPoint(x1,0,0,size),
               g.addPoint(x1,3,0,size), g.addPoint(x0,3,0,size)]
        ls = [g.addLine(pts[i], pts[(i+1) % 4]) for i in range(4)]
        g.mesh.setTransfiniteCurve(ls[1] if x1 == 4 else ls[3], n)
        g.addPlaneSurface([g.addCurveLoop(ls)]); g.synchronize()
        gmsh.model.mesh.generate(2)
        V = np.array(gmsh.model.mesh.getNodes()[1]).reshape(-1, 3)
        gmsh.finalize()
        return np.array(sorted(V[np.abs(V[:, 0] - 4) < 1e-7][:, 1].round(6).tolist()))

    return plate(0, 4), plate(4, 8)


def report(label, pairs):
    for value, (a, b) in pairs:
        ok = len(a) == len(b) and np.allclose(a, b)
        print("{:10} target={:<5} edge {:>2}/{:<2} -> {}".format(
            label, value, len(a), len(b), "CONFORMING" if ok else "MISMATCH"))


if __name__ == "__main__":
    print()
    report("cgal", [(t, cgal_shared_edge(t)) for t in (0.5, 0.75)])
    report("gmsh", [(t, gmsh_shared_edge(t)) for t in (0.3, 0.5, 0.75)])
