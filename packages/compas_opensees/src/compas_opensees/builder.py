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

Surfaces are not built. The builder refuses a model with surfaces rather
than silently dropping them.
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


class ModelBuilder:
    def __init__(self, ops, structural_model, stations=9):
        self.ops = ops
        self.model = structural_model
        # OpenSees' Lobatto integration allows at most 10 points.
        self.stations = max(2, min(10, int(stations)))
        self.built = BuiltModel()
        self._next_ghost = GHOST_TAG_BASE
        self._next_material = 1
        self._next_transf = 1
        self._next_section = 1

    # ------------------------------------------------------------------ public

    def build(self):
        ops = self.ops
        model = self.model
        if model.surfaces:
            raise NotImplementedError(
                "The OpenSees backend builds beams only for now ({} surfaces in the model). "
                "Use rfem for plate models.".format(len(model.surfaces)))

        ops.wipe()
        ops.model("basic", "-ndm", 3, "-ndf", 6)

        self._nodes()
        self._supports()
        self._members()
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
