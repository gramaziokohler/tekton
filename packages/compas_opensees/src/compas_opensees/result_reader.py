"""OpenSees state -> StructuralResultSet, after a solved load case.

- Nodes: ``nodeDisp`` (global, m / rad) and ``nodeReaction`` at supported
  nodes (kN / kNm), straight into :class:`StructuralNodeResult`.
- Beams: section forces at the Lobatto stations (``sectionForce``: P, Mz,
  My, T) with the station's 0..1 position; shear is not a section force in
  a force-based element, so it is interpolated linearly between the end
  forces (``eleResponse localForce``) - exact for uniform loads, marked in
  the sample metadata.
- Rigid links: end forces only (two stations).
- Displacement along a beam: the section moments at the stations give the
  curvature M/EI, integrated twice and pinned to the end displacements (the
  ghost node's, where a release sits). Exact for polynomial moment lines,
  which is what a beam under nodal and uniform loads has.

Signs: calibrated against RFEM (see conventions.py) - N, My, Mz, T as
OpenSees reports them, the interpolated shear negated.
"""

from compas.geometry import Vector

from compas.geometry import Point

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSurfaceResult

from compas_opensees.conventions import MY_SIGN
from compas_opensees.conventions import MZ_SIGN
from compas_opensees.conventions import SHEAR_SIGN


def _integrate_curvature(ts, curvatures, length, w_i, w_j):
    """Deflection at the stations from the curvature samples, with the end deflections as boundary values.

    The moment line of a beam under nodal and uniform loads is a polynomial,
    and the Lobatto stations interpolate a polynomial of their count minus
    one exactly. So: fit that polynomial through the samples, integrate it
    twice analytically (w(0) = w'(0) = 0), and add the linear term that
    makes w meet w_j at the far end - the part the end rotations supply.
    """
    import numpy as np

    n = len(ts)
    xs = np.array(ts, dtype=float) * length
    kappa = np.array(curvatures, dtype=float)
    if n < 2 or length <= 0:
        return [w_i] * n
    poly = np.polynomial.Polynomial.fit(xs, kappa, deg=min(n - 1, 8))
    particular = poly.integ(2, lbnd=0.0)
    part = particular(xs)
    c = (w_j - w_i - part[-1]) / length
    return [float(w_i + part[k] + c * xs[k]) for k in range(n)]


def _station_displacements(ops, built, member_id, params, moments_y, moments_z):
    """Global displacement vectors at the stations of a beam member.

    Axial: linear between the end nodes. Transverse: the curvature M/EI from
    the section moments at the stations, integrated twice, pinned to the end
    displacements (the ghost node's, where a release sits). Signs, checked
    against the closed-form sag: w'' = -My / EIy (a sagging beam under a
    downward load has My < 0 in OpenSees' raw convention), v'' = +Mz / EIz.
    """
    x, y, z = built.member_axes[member_id]
    length = built.member_length[member_id]
    ei_y, ei_z = built.member_stiffness[member_id]
    i_tag, j_tag = built.member_end_tags[member_id]

    def local(tag):
        d = list(ops.nodeDisp(tag))
        u = Vector(d[0], d[1], d[2])
        return u.dot(x), u.dot(y), u.dot(z)

    ui, vi, wi = local(i_tag)
    uj, vj, wj = local(j_tag)
    ws = _integrate_curvature(params, [-m / ei_y for m in moments_y], length, wi, wj)
    vs = _integrate_curvature(params, [m / ei_z for m in moments_z], length, vi, vj)
    out = []
    for k, t in enumerate(params):
        u, v, w = ui + (uj - ui) * t, vs[k], ws[k]
        out.append(Vector(u * x.x + v * y.x + w * z.x, u * x.y + v * y.y + w * z.y, u * x.z + v * y.z + w * z.z))
    return out


def read_case(ops, model, built, case, stations):
    node_results = {}
    for node in model.nodes:
        tag = built.node_tags.get(node.id)
        if tag is None:
            continue
        d = list(ops.nodeDisp(tag))
        result = StructuralNodeResult(
            node_id=node.id,
            load_case_id=case.id,
            displacement=Vector(d[0], d[1], d[2]),
            rotation=Vector(d[3], d[4], d[5]) if len(d) >= 6 else Vector(0, 0, 0),
        )
        if node.id in built.support_nodes:
            r = list(ops.nodeReaction(tag))
            result.reaction_force = Vector(r[0], r[1], r[2])
            result.reaction_moment = Vector(r[3], r[4], r[5]) if len(r) >= 6 else Vector(0, 0, 0)
        node_results[node.id] = result

    member_results = {}
    for member in model.members:
        tag = built.member_elements.get(member.id)
        if tag is None:
            continue
        length = built.member_length[member.id]
        end = list(ops.eleResponse(tag, "localForce"))  # [N, Vy, Vz, T, My, Mz] at i, then at j
        if len(end) < 12:
            continue
        vy_i, vz_i, vy_j, vz_j = end[1], end[2], end[7], end[8]
        rows = []
        if built.member_kind.get(member.id) == "beam":
            positions = built.member_stations[member.id]
            params = [min(max(x / length, 0.0), 1.0) if length else 0.0 for x in positions]
            raw_my = [float(ops.sectionForce(tag, k, 3)) for k in range(1, len(params) + 1)]
            raw_mz = [float(ops.sectionForce(tag, k, 2)) for k in range(1, len(params) + 1)]
            displacements = _station_displacements(ops, built, member.id, params, raw_my, raw_mz)
            for index, t in enumerate(params, start=1):
                rows.append(StructuralMemberResult(
                    member_id=member.id,
                    load_case_id=case.id,
                    position=t,
                    axial=float(ops.sectionForce(tag, index, 1)),
                    shear_y=SHEAR_SIGN * (vy_i - (vy_i + vy_j) * t),
                    shear_z=SHEAR_SIGN * (vz_i - (vz_i + vz_j) * t),
                    torsion=float(ops.sectionForce(tag, index, 4)),
                    moment_y=MY_SIGN * float(ops.sectionForce(tag, index, 3)),
                    moment_z=MZ_SIGN * float(ops.sectionForce(tag, index, 2)),
                    displacement=displacements[index - 1],
                    metadata={"position_normalized": True, "shear_interpolated": True, "displacement_interpolated": True},
                ))
        else:
            # End forces are the forces on the element's ends; the internal
            # force at a cut next to end i is their negative, next to end j
            # the force itself. Moments then take the same sign flip as the
            # section forces of the beams.
            for t, offset, sign in ((0.0, 0, -1.0), (1.0, 6, 1.0)):
                n, vy, vz, mt, my, mz = (sign * end[offset + k] for k in range(6))
                rows.append(StructuralMemberResult(
                    member_id=member.id,
                    load_case_id=case.id,
                    position=t,
                    axial=n,
                    shear_y=SHEAR_SIGN * vy,
                    shear_z=SHEAR_SIGN * vz,
                    torsion=mt,
                    moment_y=MY_SIGN * my,
                    moment_z=MZ_SIGN * mz,
                    metadata={"position_normalized": True, "end_forces_only": True},
                ))
        member_results[member.id] = rows

    surface_results = read_surfaces(ops, model, built, case)

    return StructuralResultSet(
        load_case_id=case.id,
        name=case.name,
        node_results=node_results,
        member_results=member_results,
        surface_results=surface_results,
        metadata={"source": "opensees", "stations": stations, "columns": {"member_forces": ["P", "Mz", "My", "T"], "shear": "interpolated from end forces"}},
    )


def read_surfaces(ops, model, built, case):
    """Sample every meshed plate at its mesh nodes.

    One sample per node of the plate's mesh, carrying the displacement. The
    mesh itself stays inside the run - the samples are points in space, so a
    later refinement changes the sampling but not the meaning, and results
    map back to the plate through its own id.

    Membrane forces and moments are left at zero for now: ``ShellDKGT``
    reports them per element in the element's own axes, and without working
    orthotropy the axis convention is not yet pinned down (see
    :meth:`ModelBuilder._surfaces`). Reporting a number whose axes we cannot
    name would be worse than reporting none.
    """
    if not getattr(built, "surface_elements", None):
        return {}

    out = {}
    for surface in getattr(model, "surfaces", []) or []:
        tags = built.surface_nodes.get(surface.id)
        if not tags:
            continue
        rows = []
        for tag in tags:
            point = built.mesh_points.get(tag) or built.node_points.get(tag)
            if point is None:
                continue
            d = list(ops.nodeDisp(int(tag)))
            rows.append(StructuralSurfaceResult(
                surface_id=surface.id,
                load_case_id=case.id,
                position=Point(*point),
                displacement=Vector(d[0], d[1], d[2]),
                metadata={"node_tag": int(tag), "from_mesh": tag in built.mesh_points},
            ))
        if rows:
            out[surface.id] = rows
    return out


__all__ = ["read_case", "read_surfaces"]
