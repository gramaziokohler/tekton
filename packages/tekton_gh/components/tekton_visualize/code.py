"""Tekton Visualize - deformed shape and colour by result value.

Three things come out, all from the same result set:

- `deformed`: the system lines as polylines through the deformed stations
  RFEM reported (11 per member), exaggerated by `exaggeration`.
- `meshes`: the rectangular sections swept along those polylines, with a
  vertex colour per station - the beams as they bend, coloured by `quantity`.
- `colours`: one colour per member (its maximum), for the flat view.

Values above the upper bound go hard red instead of interpolating further: an
exceedance should catch the eye, not fade out gently. Without `high` the
scale runs to the model's maximum, so the picture is readable on first
connect; a fixed bound is for comparing runs.

The geometry arithmetic lives in `tekton_gh.visualize` (pure, tested); this
script only converts to Rhino types.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Visualize"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
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


def _rhino_mesh(vertices, faces, colours):
    import Rhino.Geometry as rg
    from System.Drawing import Color

    mesh = rg.Mesh()
    for x, y, z in vertices:
        mesh.Vertices.Add(x, y, z)
    for face in faces:
        mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
    for r, g, b in colours:
        mesh.VertexColors.Add(Color.FromArgb(r, g, b))
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore
quantity: str  # type: ignore
exaggeration: float  # type: ignore
low: float  # type: ignore
high: float  # type: ignore
mesh: bool  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'quantity' the moment the component lands on the canvas. Needs
# the repo path for the import; without it the menu simply does not appear
# and TektonInfo says what is missing.
try:
    _setup()
    from tekton_gh.rhino_io import attach_value_list

    attach_value_list(ghenv, ['displacement', 'N', 'Vy', 'Vz', 'Mt', 'My', 'Mz'], param_index=2, nickname="Quantity")  # type: ignore # noqa: F821
except Exception:
    pass

geometry = []
deformed = []
meshes = []
colours = []
values = []
legend = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    import Rhino.Geometry as rg

    from tekton_gh.rhino_io import colour_ramp, member_lines

    # Rhino keeps modules for the life of the process; reload so an edit to
    # visualize.py shows on the next solve instead of after a restart.
    import importlib
    import tekton_gh.visualize
    importlib.reload(tekton_gh.visualize)
    from tekton_gh.visualize import QUANTITIES, SURFACE_QUANTITIES, deformed_polyline, member_stations, section_mesh, surface_corner_stations, surface_outline, surface_stations

    units = getattr(structural, "source_units", "m")
    scale = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(units, 1.0)
    geometry = member_lines(structural, scale=scale)

    quantity = quantity or "displacement"
    if quantity not in QUANTITIES and quantity not in SURFACE_QUANTITIES:
        _warn("Unknown quantity '{}'. Members: {}. Surfaces: {}.".format(
            quantity, ", ".join(sorted(QUANTITIES)), ", ".join(sorted(SURFACE_QUANTITIES))))
        quantity = "displacement"
    factor = 1.0 if exaggeration is None else float(exaggeration)
    build_mesh = True if mesh is None else bool(mesh)

    results = getattr(structural, "results", {}) or {}
    result_set = None
    case_id = None
    if results:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)
        if result_set is None:
            _warn("No results for load case {}. Available: {}.".format(case_id, sorted(results)))
    else:
        _warn("No results - undeformed, coloured neutrally.")

    sections = {section.id: section for section in getattr(structural, "sections", [])}

    # Stations first, so the scale can default to the model maximum.
    per_member = []
    for member in structural.members:
        stations = member_stations(structural, result_set, member, quantity)
        per_member.append((member, stations))
        values.append(max((s.value for s in stations), default=0.0))
    per_surface = []
    for surface in getattr(structural, "surfaces", []) or []:
        stations = surface_stations(structural, result_set, surface, quantity)
        per_surface.append((surface, stations))
        values.append(max((s.value for s in stations), default=0.0))

    lo = 0.0 if low is None else float(low)
    if high is not None:
        hi = float(high)
    elif quantity == "utilization":
        hi = 1.0
    else:
        hi = max(values) if values and max(values) > 0.0 else 1.0

    for member, stations in per_member:
        points = deformed_polyline(stations, exaggeration=factor, scale=scale)
        deformed.append(rg.PolylineCurve([rg.Point3d(p.x, p.y, p.z) for p in points]))

        section = sections.get(member.section_id)
        # Couplings and rigid links have no section; they are lines only.
        if build_mesh and section is not None and section.width > 0 and section.height > 0:
            vertices, faces, vertex_colours = section_mesh(
                points,
                section.width * scale,
                section.height * scale,
                member.orientation_vector,
                values=[s.value for s in stations],
                low=lo,
                high=hi,
            )
            meshes.append(_rhino_mesh(vertices, faces, vertex_colours))

    # Surfaces: the result mesh nodes (or the corners) as a tessellated,
    # deformed, vertex-coloured mesh. Rhino triangulates the sample points in
    # the surface's plane; a plate that bends shows it, because every mesh
    # node carries its own displacement.
    for surface, stations in per_surface:
        if len(stations) < 3:
            continue
        outline = surface_outline(structural, surface)
        if len(outline) < 3:
            continue
        o = [rg.Point3d(p.x * scale, p.y * scale, p.z * scale) for p in outline]
        plane = rg.Plane(o[0], o[1], o[2])
        flat = [rg.Point3d(s.point.x * scale, s.point.y * scale, s.point.z * scale) for s in stations]
        mesh_ = None
        try:
            mesh_ = rg.Mesh.CreateFromTessellation(flat, None, plane, False)
        except Exception:
            mesh_ = None
        if mesh_ is None or mesh_.Vertices.Count != len(flat):
            # Fallback: the outline as a fan; stations are then the corners.
            mesh_ = rg.Mesh()
            for p in o:
                mesh_.Vertices.Add(p)
            for i in range(1, len(o) - 1):
                mesh_.Faces.AddFace(0, i, i + 1)
            stations = surface_corner_stations(structural, result_set, surface) if len(stations) != len(o) else stations
        for i, s in enumerate(stations[:mesh_.Vertices.Count]):
            p = s.deformed(factor, scale)
            mesh_.Vertices.SetVertex(i, p.x, p.y, p.z)
        mesh_.VertexColors.Clear()
        for s in stations[:mesh_.Vertices.Count]:
            mesh_.VertexColors.Add(colour_ramp(s.value, lo, hi))
        mesh_.Normals.ComputeNormals()
        meshes.append(mesh_)
        corners = [rg.Point3d(*st.deformed(factor, scale)) for st in surface_corner_stations(structural, result_set, surface)]
        deformed.append(rg.PolylineCurve(corners + corners[:1]))

    colours = [colour_ramp(value, lo, hi) for value in values]

    unit_of = {"displacement": "m", "utilization": "-"}
    legend = [
        "Quantity: {} [{}]".format(quantity, unit_of.get(quantity, "kN / kNm")),
        "Load case: {}".format(case_id if case_id is not None else "-"),
        "Scale: {:.3g} .. {:.3g}{}".format(lo, hi, "" if high is not None else " (auto: model maximum)"),
        "Maximum in the model: {:.4g}".format(max(values) if values else 0.0),
        "Deformation x {:g}".format(factor),
    ]
    if values and high is not None and max(values) > hi:
        _warn("Maximum value {:.4g} is above the scale upper bound {:.4g}.".format(max(values), hi))
    if result_set is not None and structural.members and not any(
        row.displacement is not None for rows in (result_set.member_results or {}).values() for row in rows
    ):
        _warn("Results carry no member deformations - the deformed shape is interpolated between nodes only. Re-run with the current reader.")

for line in legend:
    print(line)
