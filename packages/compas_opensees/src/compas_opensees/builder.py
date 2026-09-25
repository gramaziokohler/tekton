"""StructuralModel -> openseespy commands.

The builder emits, in this order: nodes, supports, one element per member,
and the ghost nodes + zeroLength elements that express releases. Loads are
not built here - they belong to a load case and are emitted per case by the
analysis loop (:mod:`compas_opensees.analysis`).

Every construction below was proven in ``tests/spike_opensees.py``:

- A **beam member** is one ``forceBeamColumn`` with an elastic section and a
  Lobatto integration of N points: the section forces are exact at the N
  stations, whose positions along the member are known (``sectionLocation``).
  One element per member keeps the neutral member id as the element tag.
- A **release** is a ghost node at the member end, the element connected to
  the ghost, and a ``zeroLength`` between node and ghost oriented along the
  member's local axes: a stiff spring for every fixed DOF, an elastic spring
  for a finite stiffness, nothing for a free DOF. One mechanism for hinges,
  springs, torsion and translation releases alike - OpenSees' own release
  codes only cover bending on ``elasticBeamColumn``, which has no stations.
- A **rigid link / coupling** is a stiff ``elasticBeamColumn`` (the material
  scaled by :data:`RIGID_FACTOR`): OpenSees' ``rigidLink`` keeps the
  kinematics but loses the reactions at the retained node.
- A **support** is ``fix`` for every infinite stiffness; finite support
  springs are a ``zeroLength`` to a fixed ghost (same construction as a
  release).

- A **surface** is meshed into triangles (see :mod:`compas_opensees.meshing`,
  gmsh, conforming along shared edges) and emitted as one ``ShellDKGT`` per
  triangle on an elastic plate section. The mesh belongs to the run, not to
  the model: results go back per plate through ``source_element_id``.
  Orthotropy is *not* modelled - see :meth:`ModelBuilder._surfaces` for the
  measurement behind that, and the warning every oriented panel gets.
"""

from compas_timber_fea.core.materials import Material as NeutralMaterial

from compas_opensees.conventions import G_ACC
from compas_opensees.conventions import RIGID_FACTOR
from compas_opensees.conventions import local_axes
from compas_opensees.conventions import section_constants
from compas_opensees.conventions import stiffness_kn_m2
from compas_opensees.conventions import to_local

#: Stiffness used for a "fixed" DOF inside a zeroLength (kN/m or kNm/rad).
#: Three to four orders above the stiffest member term keeps the matrix
#: well-conditioned in double precision.
FIXED_DOF_STIFFNESS = 1.0e10

#: Ghost node tags start here, so they never collide with neutral node ids.
GHOST_TAG_BASE = 1_000_000

INF = float("inf")


def line_support_stiffnesses(model, support_id):
    """Per-node stiffness for a line support, by tributary length.

    The neutral model stores kN/m per metre of line, because that is what a
    line support *is* and what RFEM takes. OpenSees only has nodal springs,
    so the per-metre value has to be multiplied by the length each node is
    responsible for: half the segment on either side, which leaves an end
    node with half of one segment.

    The invariant this exists for: the sum over the chain is the per-metre
    value times the total length, whatever the node spacing. Refining the
    mesh must not stiffen the support.

    ``inf`` passes through untouched - infinitely rigid per metre is
    infinitely rigid per node, and multiplying it by a length would be
    meaningless. ``0.0`` likewise stays free.

    Parameters
    ----------
    model : :class:`StructuralModel`
    support_id : int

    Returns
    -------
    dict
        ``{node id: {"ux": k, ... "rz": k}}`` in nodal units (kN/m, kNm/rad).

    Raises
    ------
    ValueError
        If the chain has fewer than two nodes, references a node that does
        not exist, or has zero length - none of which can be distributed
        over, and all of which would otherwise divide by zero or silently
        produce a support that holds nothing.
    """
    support = next((s for s in model.line_supports if s.id == support_id), None)
    if support is None:
        raise ValueError("no line support with id {}".format(support_id))
    if len(support.nodes or []) < 2:
        raise ValueError("line support {} has fewer than two nodes".format(support_id))

    points = {node.id: node.point for node in model.nodes}
    missing = [n for n in support.nodes if n not in points]
    if missing:
        raise ValueError("line support {} references unknown nodes {}".format(support_id, missing))

    chain = [points[n] for n in support.nodes]
    segments = [chain[i].distance_to_point(chain[i + 1]) for i in range(len(chain) - 1)]
    total = sum(segments)
    if total < 1e-9:
        raise ValueError("line support {} has zero length".format(support_id))

    tributary = {}
    for index, node_id in enumerate(support.nodes):
        before = segments[index - 1] if index > 0 else 0.0
        after = segments[index] if index < len(segments) else 0.0
        tributary[node_id] = (before + after) / 2.0

    per_metre = {
        "ux": support.ux, "uy": support.uy, "uz": support.uz,
        "rx": support.rx, "ry": support.ry, "rz": support.rz,
    }
    return {
        node_id: {
            dof: value if value in (0.0, INF) else value * length
            for dof, value in per_metre.items()
        }
        for node_id, length in tributary.items()
    }


class BuiltModel:
    """What the analysis and the reader need to know about the built model."""

    def __init__(self):
        self.member_elements = {}      # member id -> element tag
        self.member_kind = {}          # member id -> "beam" | "rigid"
        self.member_axes = {}          # member id -> (x, y, z) unit vectors
        self.member_length = {}        # member id -> length (m)
        self.member_stations = {}      # member id -> [absolute positions along the member]
        self.member_self_weight = {}   # member id -> kN/m (positive magnitude), for self-weight cases
        self.node_tags = {}            # neutral node id -> ops node tag (identity today)
        self.support_nodes = []        # neutral node ids that carry a support
        self.release_elements = {}     # (member id, "start"|"end") -> zeroLength tag
        self.member_end_tags = {}      # member id -> (i tag, j tag) the element actually connects to
        self.member_stiffness = {}     # member id -> (E*Iy, E*Iz) in kN m2, for the deflection line
        self.free_dofs = 0             # 6 per node minus the fixed ones; zero means LAPACK would kill the process
        self.warnings = []
        # --- surfaces (WP0b) ---
        self.surface_elements = {}     # surface id -> [element tags]
        self.surface_nodes = {}        # surface id -> [node tags of its mesh]
        self.surface_area = {}         # surface id -> m2
        self.surface_self_weight = {}  # surface id -> kN/m2 (positive magnitude)
        self.mesh_points = {}          # generated node tag -> (x, y, z)
        self.node_points = {}          # neutral node id -> (x, y, z), for area loads
        self.mesh = None               # the MeshResult, for the reader


class ModelBuilder:
    def __init__(self, ops, structural_model, stations=9, mesh_target_length=None):
        self.ops = ops
        self.model = structural_model
        # OpenSees' Lobatto integration allows at most 10 points.
        self.stations = max(2, min(10, int(stations)))
        self.mesh_target_length = mesh_target_length
        self.built = BuiltModel()
        self._next_ghost = GHOST_TAG_BASE
        self._next_material = 1
        self._next_transf = 1
        self._next_section = 1
        self._next_element = 1_000_000   # surface elements, clear of member ids

    # ------------------------------------------------------------------ public

    def build(self):
        ops = self.ops
        model = self.model

        # Surfaces are meshed before anything is emitted: the mesh introduces
        # nodes, and they have to exist before an element references them.
        mesh = None
        if model.surfaces:
            from compas_opensees.meshing import DEFAULT_TARGET_LENGTH
            from compas_opensees.meshing import mesh_surfaces

            target = self.mesh_target_length or DEFAULT_TARGET_LENGTH
            mesh = mesh_surfaces(model, target)
            self.built.mesh = mesh
            self.built.mesh_points = mesh.points
            self.built.warnings.extend(mesh.warnings)

        ops.wipe()
        ops.model("basic", "-ndm", 3, "-ndf", 6)

        self._nodes()
        if mesh is not None:
            self._mesh_nodes(mesh)
        self._supports()
        self._line_supports()
        self._members()
        if mesh is not None:
            self._surfaces(mesh)
        # A system without a free DOF (every node fully fixed) does not fail,
        # it aborts the process inside LAPACK. Refuse it here instead.
        if self.built.free_dofs <= 0 and self._next_ghost == GHOST_TAG_BASE:
            raise ValueError("Nothing to solve: every degree of freedom of every node is fixed.")
        return self.built

    # ----------------------------------------------------------------- pieces

    def _nodes(self):
        for node in self.model.nodes:
            self.ops.node(int(node.id), float(node.point.x), float(node.point.y), float(node.point.z))
            self.built.node_tags[node.id] = int(node.id)
            self.built.node_points[int(node.id)] = (
                float(node.point.x), float(node.point.y), float(node.point.z))
            self.built.free_dofs += 6

    def _supports(self):
        for support in self.model.supports:
            values = [support.ux, support.uy, support.uz, support.rx, support.ry, support.rz]
            fixed = [1 if v == INF else 0 for v in values]
            springs = [(i, v) for i, v in enumerate(values) if v not in (0.0, INF)]
            for node_id in support.nodes:
                if node_id not in self.built.node_tags:
                    self.built.warnings.append("support {} on unknown node {}".format(support.id, node_id))
                    continue
                if any(fixed):
                    self.ops.fix(int(node_id), *fixed)
                    self.built.free_dofs -= sum(fixed)
                if springs:
                    self._support_springs(node_id, springs)
                self.built.support_nodes.append(node_id)

    def _line_supports(self):
        """A line support, distributed over its chain.

        OpenSees has no line support. The neutral values are kN/m per metre,
        so each node gets the per-metre stiffness times its tributary length:
        half a segment on each side, one segment for an end node. Splitting
        evenly instead would stiffen the ends and make the answer depend on
        the mesh density.
        """
        for support in self.model.line_supports:
            try:
                per_node = line_support_stiffnesses(self.model, support.id)
            except ValueError as error:
                self.built.warnings.append("line support {}: {}".format(support.id, error))
                continue

            for node_id, values in per_node.items():
                if node_id not in self.built.node_tags:
                    self.built.warnings.append(
                        "line support {} on unknown node {}".format(support.id, node_id))
                    continue
                ordered = [values[dof] for dof in ("ux", "uy", "uz", "rx", "ry", "rz")]
                fixed = [1 if v == INF else 0 for v in ordered]
                springs = [(i, v) for i, v in enumerate(ordered) if v not in (0.0, INF)]
                if any(fixed):
                    self.ops.fix(int(node_id), *fixed)
                    self.built.free_dofs -= sum(fixed)
                if springs:
                    self._support_springs(node_id, springs)
                self.built.support_nodes.append(node_id)

    def _support_springs(self, node_id, springs):
        """Finite support stiffness: a zeroLength to a fully fixed ghost, global axes."""
        node = next(n for n in self.model.nodes if n.id == node_id)
        ghost = self._ghost(node.point)
        self.ops.fix(ghost, 1, 1, 1, 1, 1, 1)
        mats, dirs = [], []
        for dof_index, k in springs:
            mats.append(self._elastic(k))
            dirs.append(dof_index + 1)
        self.ops.element("zeroLength", self._ghost_tag(), ghost, int(node_id), "-mat", *mats, "-dir", *dirs)

    def _members(self):
        points = {n.id: n.point for n in self.model.nodes}
        sections = {s.id: s for s in self.model.sections}
        for member in self.model.members:
            start, end = points.get(member.node_start), points.get(member.node_end)
            if start is None or end is None:
                self.built.warnings.append("member {} references a missing node".format(member.id))
                continue
            axes = local_axes(start, end, member.orientation_vector)
            length = start.distance_to_point(end)
            if length < 1e-9:
                self.built.warnings.append("member {} has zero length - skipped".format(member.id))
                continue
            self.built.member_axes[member.id] = axes
            self.built.member_length[member.id] = length

            section = sections.get(member.section_id)
            material = self._material(section.material_id if section else 1)
            e = stiffness_kn_m2(material.E0_mean)
            g = stiffness_kn_m2(material.G_mean) if material.G_mean else e / 16.0

            i_tag = self._end_node(member, "start", member.node_start, axes)
            j_tag = self._end_node(member, "end", member.node_end, axes)
            self.built.member_end_tags[member.id] = (i_tag, j_tag)

            transf = self._next_transf
            self._next_transf += 1
            z = axes[2]
            self.ops.geomTransf("Linear", transf, float(z.x), float(z.y), float(z.z))

            rigid = member.member_type in ("RIGID", "COUPLING") or getattr(member, "is_rigid", False) or section is None or section.width <= 0 or section.height <= 0
            if rigid:
                area, iy, iz, j = section_constants(0.2, 0.2)
                self.ops.element("elasticBeamColumn", int(member.id), i_tag, j_tag, area, e * RIGID_FACTOR, g * RIGID_FACTOR, j, iy, iz, transf)
                self.built.member_kind[member.id] = "rigid"
                self.built.member_stations[member.id] = [0.0, length]
                self.built.member_self_weight[member.id] = 0.0
            else:
                area, iy, iz, j = section_constants(section.width, section.height)
                sec_tag = self._next_section
                self._next_section += 1
                self.ops.section("Elastic", sec_tag, e, area, iz, iy, g, j)
                self.ops.beamIntegration("Lobatto", sec_tag, sec_tag, self.stations)
                self.ops.element("forceBeamColumn", int(member.id), i_tag, j_tag, transf, sec_tag)
                self.built.member_kind[member.id] = "beam"
                self.built.member_stiffness[member.id] = (e * iy, e * iz)
                self.built.member_stations[member.id] = [float(x) for x in self.ops.sectionLocation(int(member.id))]
                # kN/m: density kg/m3 * g / 1000 * area
                self.built.member_self_weight[member.id] = material.density_mean * G_ACC / 1000.0 * area
            self.built.member_elements[member.id] = int(member.id)

    def _end_node(self, member, which, node_id, axes):
        """The tag the element connects to at this end: the node, or a ghost behind a zeroLength."""
        release = getattr(member, "release_{}".format(which), None)
        if release is None or release.is_rigid():
            return int(node_id)
        node = next(n for n in self.model.nodes if n.id == node_id)
        ghost = self._ghost(node.point)
        values = [release.ux, release.uy, release.uz, release.rx, release.ry, release.rz]
        mats, dirs = [], []
        for dof_index, value in enumerate(values):
            if value == 0.0:
                continue  # free
            mats.append(self._elastic(FIXED_DOF_STIFFNESS if value == INF else value))
            dirs.append(dof_index + 1)
        x, y = axes[0], axes[1]
        tag = self._ghost_tag()
        self.ops.element(
            "zeroLength", tag, int(node_id), ghost,
            "-mat", *mats, "-dir", *dirs,
            "-orient", float(x.x), float(x.y), float(x.z), float(y.x), float(y.y), float(y.z),
        )
        self.built.release_elements[(member.id, which)] = tag
        return ghost

    # ---------------------------------------------------------------- helpers

    def _mesh_nodes(self, mesh):
        """Nodes the mesher generated. The outline keeps its neutral ids."""
        for tag, (x, y, z) in sorted(mesh.points.items()):
            self.ops.node(int(tag), float(x), float(y), float(z))
            self.built.free_dofs += 6

    def _surfaces(self, mesh):
        """One ShellDKGT per triangle, with an elastic plate section per thickness.

        ``ShellDKGT`` was validated against the Navier solution for a simply
        supported square plate: -4.1 % on a coarse mesh, -0.4 % at 12x12
        divisions (``tests/spike_opensees_shells.py``). The triangle is the
        right element here because gmsh gives us triangles.

        **Orthotropy is not modelled.** Timber panels are markedly stiffer
        along the face grain, and the honest route - ``ElasticOrthotropic``
        wrapped in ``PlateFiber`` inside a ``LayeredShell`` - builds without
        error but does *not* transport the direction: a 30:1 stiffness ratio
        came out as 1.2:1 in deflection, while the same test on an isotropic
        section reproduced a factor of 30 exactly. So the section is isotropic
        along the stronger axis, which is conservative across the span and
        unconservative across it. Every model with a ``span_direction`` gets a
        warning saying so. Resolving it properly needs either a material with
        working axes or an equivalent-stiffness formulation per direction -
        WP0b's open item, and the reason plates still go to RFEM when the
        answer has to be defensible.
        """
        thicknesses = {t.id: t for t in getattr(self.model, "thicknesses", [])}
        section_cache = {}
        oriented = []

        for surface in self.model.surfaces:
            meshed = mesh.surfaces.get(surface.id)
            if meshed is None:
                continue
            thickness = thicknesses.get(surface.thickness_id)
            if thickness is None:
                self.built.warnings.append(
                    "surface {} references unknown thickness {} - skipped".format(
                        surface.id, surface.thickness_id))
                continue

            material = self._material(thickness.material_id)
            key = (thickness.id, material.name)
            if key not in section_cache:
                section_cache[key] = self._plate_section(material, thickness.thickness)
            section_tag = section_cache[key]

            if getattr(surface, "span_direction", None) is not None:
                oriented.append(surface.id)

            tags = []
            for triangle in meshed.triangles:
                tag = self._next_element
                self._next_element += 1
                self.ops.element("ShellDKGT", tag, *(int(node) for node in triangle), section_tag)
                tags.append(tag)

            self.built.surface_elements[surface.id] = tags
            self.built.surface_nodes[surface.id] = list(meshed.node_tags)
            self.built.surface_area[surface.id] = meshed.area
            # kN/m2, positive magnitude - the analysis loop applies the sign.
            self.built.surface_self_weight[surface.id] = (
                material.density_mean * G_ACC / 1000.0 * float(thickness.thickness)
            )

        if oriented:
            self.built.warnings.append(
                "span_direction is set on {} surface(s) but the shell section is isotropic: "
                "OpenSees' orthotropic plate path does not transport the material axes "
                "(measured). Panel results are therefore direction-agnostic - use rfem "
                "when the anisotropy matters.".format(len(oriented)))

    def _plate_section(self, material, thickness):
        """An elastic plate section for a panel of this material and thickness."""
        tag = self._next_section
        self._next_section += 1
        self.ops.section(
            "ElasticMembranePlateSection",
            tag,
            stiffness_kn_m2(material.E0_mean),
            float(material.poisson or 0.0),
            float(thickness),
            0.0,   # mass density: self-weight is applied as a load, not by the element
        )
        return tag

    def _material(self, material_id):
        raw = (self.model.materials or {}).get(material_id, "C24")
        return NeutralMaterial.resolve(raw)

    def _elastic(self, k):
        tag = self._next_material
        self._next_material += 1
        self.ops.uniaxialMaterial("Elastic", tag, float(k))
        return tag

    def _ghost(self, point):
        tag = self._ghost_tag()
        self.ops.node(tag, float(point.x), float(point.y), float(point.z))
        return tag

    def _ghost_tag(self):
        self._next_ghost += 1
        return self._next_ghost


def member_uniform_load(built, member_id, force_global):
    """Global force per length -> the (Wy, Wz, Wx) OpenSees wants for ``-beamUniform``."""
    axes = built.member_axes[member_id]
    wx, wy, wz = to_local(force_global, axes)
    return wy, wz, wx


__all__ = ["ModelBuilder", "BuiltModel", "member_uniform_load", "FIXED_DOF_STIFFNESS"]
