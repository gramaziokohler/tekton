import math

from compas.geometry import Point
from compas.geometry import Vector
from compas_timber.structural import StructuralSegment
from compas_timber.structural import StructuralGraph
from compas_timber.structural import BeamStructuralElementSolver

from tekton_core.core.model import StructuralLoadCase
from tekton_core.core.joint_policy import PlateConnectionPolicy
from tekton_core.core.joint_policy import policy_from_connector_mode
from tekton_core.core.materials import Material
from tekton_core.core.units import check_section_plausible
from tekton_core.core.units import check_thickness_plausible
from tekton_core.core.units import scale_to_meters

from .core.model import StructuralMember
from .core.model import StructuralMemberSet
from .core.model import StructuralModel
from .core.model import StructuralNode
from .core.model import StructuralSection
from .core.model import StructuralLineSupport
from .core.model import StructuralSupport
from .core.model import StructuralThickness
from .core.model import StructuralSurface
from .core.model import StructuralSurfaceConnection


#: Dimensions closer than this (in metres) are treated as the same catalogue
#: entry. Geometry derived from CAD carries float noise well below a tenth of
#: a millimetre, which must not produce duplicate sections or thicknesses.
DIMENSION_TOLERANCE = 1e-5

#: A plate's outer contour and its openings are both `FreeContour` features.
#: What separates them is `counter_sink`, which compas_timber sets from the
#: `interior` flag: the outline is built with interior=False, every opening
#: with interior=True (see compas_timber.elements.plate.Plate.features).
#: `tool_position` only records which side the cutter runs on, and that
#: follows the contour's winding relative to the plate's reference side - for
#: an outline built by `Plate.from_outline_thickness` it comes out "right"
#: whichever way the outline is wound, so reading it as "opening" turns every
#: plate's own boundary into a phantom hole.
OPENING_COUNTER_SINK = True

#: Kept for the older path: when a feature carries no `counter_sink` at all,
#: the cutter side is the only hint left.
OPENING_TOOL_POSITION = "right"


def _release_from(value):
    """A MemberRelease from a beam's end_releases entry: a preset name, a release, or None."""
    from tekton_core.core.releases import MemberRelease

    if value is None or isinstance(value, MemberRelease):
        return value
    name = str(value).strip().lower()
    presets = {"pinned": MemberRelease.pinned, "hinged": MemberRelease.pinned,
               "spherical": MemberRelease.spherical, "rigid": MemberRelease.rigid}
    if name not in presets:
        raise ValueError("end release {!r}: use one of {}".format(value, ", ".join(sorted(presets))))
    release = presets[name]()
    return None if release.is_rigid() else release


def _chain(members):
    """The members ordered end to end, or None when they do not form one open chain."""
    ends = {}
    for m in members:
        for node in (m.node_start, m.node_end):
            ends.setdefault(node, []).append(m)
    if any(len(v) > 2 for v in ends.values()):
        return None
    tips = [node for node, v in ends.items() if len(v) == 1]
    if len(tips) != 2:
        return None
    ordered, node, used = [], tips[0], set()
    while True:
        nxt = [m for m in ends[node] if m.id not in used]
        if not nxt:
            break
        m = nxt[0]
        used.add(m.id)
        ordered.append(m)
        node = m.node_end if m.node_start == node else m.node_start
    return ordered if len(ordered) == len(members) else None


def _dimension_key(*values):
    """Round dimensions so float noise does not create duplicate entries."""
    digits = max(0, -int(round(math.log10(DIMENSION_TOLERANCE))))
    return tuple(round(v, digits) if isinstance(v, (int, float)) else v for v in values)


class SectionLibrary:
    """Will keep track of created sections to avoid duplicates. Sections are defined by their dimensions and shape type."""

    def __init__(self):
        self.model_sections = None
        self.sections_map = {}
        self._section_id_counter = 1

    def create_section(self, name, width, height, shape, material_id):
        # The material is part of the key: a C24 and a GL24h beam of the same
        # dimensions are two sections, not one. Leaving it out silently gave
        # every beam the material of whichever one was translated first.
        key = _dimension_key(width, height, shape, material_id)
        if key in self.sections_map:
            raise ValueError(f"Section with dimensions {width}x{height} and shape {shape} already exists.")
        sec_id = self._section_id_counter

        section = StructuralSection(id=sec_id, name=name, width=width, height=height, shape_type=shape, material_id=material_id)
        self.model_sections.append(section)
        self.sections_map[key] = section
        self._section_id_counter += 1
        return section

    def get_or_create_section(self, width, height, shape, material_id):
        key = _dimension_key(width, height, shape, material_id)
        if key not in self.sections_map:
            name = f"R_M{material_id} {width}/{height}"
            self.create_section(name, width, height, shape, material_id)
        return self.sections_map[key]

class ThicknessLibrary:
    """Will keep track of created thicknesses to avoid duplicates."""

    def __init__(self):
        self.model_thicknesses = None
        self.thicknesses_map = {}
        self._thickness_id_counter = 1

    def create_thickness(self, name, thickness_val, material_id):
        key = _dimension_key(thickness_val, material_id)
        if key in self.thicknesses_map:
            raise ValueError(f"Thickness {thickness_val} already exists.")
        t_id = self._thickness_id_counter

        thickness = StructuralThickness(id=t_id, name=name, material_id=material_id, thickness=thickness_val)
        self.model_thicknesses.append(thickness)
        self.thicknesses_map[key] = thickness
        self._thickness_id_counter += 1
        return thickness

    def get_or_create_thickness(self, thickness_val, material_id):
        key = _dimension_key(thickness_val, material_id)
        if key not in self.thicknesses_map:
            name = f"Thickness {thickness_val:.3f}m"
            self.create_thickness(name, thickness_val, material_id)
        return self.thicknesses_map[key]


#: Ids are derived from a source identity rather than from iteration order, so
#: an untouched element keeps its numbers when the model around it is edited.
#: The derivation is a hash, because the backends want a positive integer and
#: the source identity is a GUID string.
#:
#: The space is 2^31, which is what RFEM accepts as an object number. With a
#: few thousand objects the chance of a collision is around one in a million;
#: :func:`_unique_id` resolves one deterministically rather than leaving two
#: objects sharing a number.
ID_SPACE = 2_147_483_647


def stable_id(*parts):
    """A positive, deterministic id for an identity made of `parts`.

    Two rules, both learned the hard way:

    * **Never include another element's identity.** An id built from a growing
      set of neighbouring GUIDs flips as soon as a neighbour sorts differently,
      and a persisted map then binds the wrong object. An id describes its own
      element and nothing else.
    * **Never include position in a list.** That is the bug this replaces:
      ``node_index`` is ``enumerate(nodes())``, so inserting one beam shifted
      every id after it.
    """
    import hashlib

    key = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big") % ID_SPACE + 1


def _unique_id(taken, *parts):
    """`stable_id` with collisions resolved, deterministically.

    A collision is improbable but not impossible, and two objects sharing an
    id would be a silent, data-dependent corruption. Rehashing with a counter
    keeps the result a pure function of the identities involved - the same
    model always produces the same ids, collision or not.
    """
    candidate = stable_id(*parts)
    attempt = 0
    while candidate in taken:
        attempt += 1
        candidate = stable_id(*parts, "collision", attempt)
    taken.add(candidate)
    return candidate


def node_to_id(sg, node):
    """Neutral id of a graph node, derived from where the node *is*.

    A node has no GUID of its own - it is created by the graph where geometry
    meets, and its graph key is an insertion index. Its position, however, is
    exactly what makes it that node: two beams share a node because they share
    a point. So the identity is the rounded coordinate.

    Rounded to a micrometre: far below anything a timber model means, far above
    the float noise a unit conversion introduces.
    """
    point = sg.node_point(node)
    return stable_id("node", round(point[0], 6), round(point[1], 6), round(point[2], 6))

def source_id(source):
    return str(getattr(source, "guid", None) or getattr(source, "id", None) or getattr(source, "name", None) or source)

class TimberToStructural:
    """Konvertiert ein compas_timber Model in ein neutrales StructuralModel.

    Parameters
    ----------
    connector_mode : str
        How virtual connector segments between non-touching centrelines are
        modelled: "rigid" or anything else for a hinge-hinge coupling.
    material_name : str
        Timber grade applied to the whole model, e.g. "C24".
    source_units : str
        Unit of the incoming timber model ("m", "cm", "mm", ...). Geometry is
        converted to metres once, here at the boundary; see
        :mod:`tekton_core.core.units`.
    """

    def __init__(self, connector_mode="rigid", material_name="C24", source_units="m", joint_policy=None, load_cases=None, plate_policy=None):
        self.connector_mode = connector_mode
        self.material_name = material_name
        self.source_units = source_units
        self.scale = scale_to_meters(source_units)
        # The joint policy carries the mechanical idealisation of the timber
        # joints. Without an explicit one, connector_mode decides, so existing
        # callers keep their behaviour.
        self.joint_policy = joint_policy or policy_from_connector_mode(connector_mode)
        self.plate_policy = plate_policy or PlateConnectionPolicy()
        # None means "seed a self-weight case"; pass a list to author your own.
        self.load_cases = load_cases
        self.sections_library = SectionLibrary()
        self.thicknesses_library = ThicknessLibrary()
        #: Member ids handed out during the current translate(), so a hash
        #: collision can be resolved rather than silently sharing a number.
        #: Reset per call - a translator reused for a second model must not
        #: carry the first model's ids into it.
        self._member_ids = set()
        self._set_keys = {}
        self._set_ids = set()
        #: Assumptions and anomalies recorded during the last translate().
        self.report = []

    def _next_member_id(self, *parts):
        return _unique_id(self._member_ids, "member", *parts)

    def _material_id_for(self, model, source):
        """Material id for one timber element, from its own grade if it has one.

        An element names its grade in ``attributes["material"]`` - a string
        like "GL24h", or a Material. Everything else falls back to the
        model-wide grade, which is what every model did before WP7.

        Grades are pooled by name, so a hundred C24 beams share one material
        entry and one section per size, the way a backend expects.
        """
        raw = None
        attributes = getattr(source, "attributes", None)
        if attributes:
            raw = attributes.get("material") or attributes.get("grade")
        if not raw:
            return 1

        material = Material.resolve(raw)
        existing = self._material_ids.get(material.name)
        if existing is not None:
            return existing

        new_id = max(model.materials) + 1 if model.materials else 1
        model.materials[new_id] = material
        self._material_ids[material.name] = new_id
        if material.is_assumed:
            self.report.append(f"material {material.name!r}: {material.standard}")
        return new_id

    def _scaled_point(self, point):
        if self.scale == 1.0:
            return point
        return Point(point.x * self.scale, point.y * self.scale, point.z * self.scale)

    def translate(self, timber_model) -> StructuralModel:
        # Sicherstellen, dass die strukturellen Segmente generiert sind
        if timber_model.beams:
             if not any(timber_model.get_beam_structural_segments(beam) for beam in timber_model.beams):
                 print("Generiere strukturelle Segmente...")
                 timber_model.create_beam_structural_segments()
             
             solver = BeamStructuralElementSolver()
             _, joints_traversed = solver.add_structural_segments(timber_model)
             solver.add_joint_structural_segments(timber_model, joints_traversed)

        if list(timber_model.plates):
            from compas_timber.structural import PlateStructuralElementSolver
            print("Generiere strukturelle Flächen...")
            # Translating the same TimberModel twice (a re-solve in
            # Grasshopper) is safe: since #866 the solver replaces the
            # surfaces and lines it stored before instead of appending.
            plate_solver = PlateStructuralElementSolver()
            plate_solver.add_structural_surfaces(timber_model)
            # Process all joints for plate-plate connections
            plate_joints = [j for j in timber_model.joints if any(hasattr(el, "outline_a") for el in j.elements)]
            plate_solver.add_joint_structural_lines(timber_model, plate_joints)

        structural_graph = StructuralGraph.from_model(timber_model)

        model = StructuralModel()
        model.source_units = self.source_units
        self.report = []
        # Per-call state. A translator reused for a second model must not
        # carry the first model's sections, thicknesses or ids into it - the
        # libraries refuse a duplicate key, so the second translate() used to
        # fail outright on the "Rigid" section.
        self._member_ids = set()
        self._set_keys = {}
        self._set_ids = set()
        self.sections_library = SectionLibrary()
        self.thicknesses_library = ThicknessLibrary()
        self.sections_library.model_sections = model.sections  # Damit die SectionLibrary direkt in das Model schreibt
        self.thicknesses_library.model_thicknesses = model.thicknesses

        # Material id 1 is the model default; elements that name their own
        # grade get an id of their own (see _material_id_for).
        self._material_ids = {}
        material = Material.resolve(self.material_name)
        model.materials[1] = material
        self._material_ids[material.name] = 1
        if material.is_assumed:
            self.report.append(f"material {material.name!r}: {material.standard}")

        self._add_nodes(model, structural_graph)
        self._add_sections_and_members(model, structural_graph)
        # Wir brauchen ein "Rigid" Section für virtuelle Stäbe
        self._add_connectors(model, structural_graph)

        if list(timber_model.plates):
            self._add_plate_surfaces(model, structural_graph)
            self._add_plate_connections(model, structural_graph)

        self._remove_zero_length_members(model)
        self._add_member_sets(model)

        # Lager nur aus explizit markierten Support-Punkten im TimberModel ableiten.
        self._add_support_nodes(model, structural_graph)
        self._add_line_supports(model, timber_model)
        self._settle_fully_released_nodes(model)

        # 4. Loads (Static Cases - Default for now)
        self._add_load_cases(model)
        return model

    def _add_load_cases(self, model):
        """Seed the model's load cases.

        A timber design model carries no loading, so the translator can only
        contribute self-weight. Anything else - imposed, snow, wind, and the
        combinations - is authored on the neutral model afterwards, where every
        backend picks it up identically.
        """
        if self.load_cases is not None:
            model.load_cases.extend(self.load_cases)
            return

        model.load_cases.append(StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True))

    def _remove_zero_length_members(self, model, tol=1e-6):
        nodes_by_id = {node.id: node for node in model.nodes}
        valid_members = []
        removed_member_ids = set()

        for member in model.members:
            start_node = nodes_by_id.get(member.node_start)
            end_node = nodes_by_id.get(member.node_end)

            if not start_node or not end_node:
                valid_members.append(member)
                continue

            if start_node.point.distance_to_point(end_node.point) <= tol:
                removed_member_ids.add(member.id)
                continue

            valid_members.append(member)

        if removed_member_ids:
            model.members = valid_members
            model.member_loads = [load for load in model.member_loads if load.member_id not in removed_member_ids]
            print(f"{len(removed_member_ids)} elements with 0 length removed.")

    def _get_support_nodes(self, model, structural_graph, tol=1e-4):
        """Match declared support points against graph nodes.

        Comparison happens in source units, before scaling, so the tolerance
        keeps its meaning regardless of the model's unit. Points that match no
        node are recorded in the report rather than dropped silently: a model
        that reaches analysis without supports is a mechanism.
        """
        by_type = {}
        unmatched = 0

        for u, v in structural_graph.beam_edges:
            beam = structural_graph.beam(u, v)
            support_points = beam.attributes.get("support_points", [])

            if not support_points:
                continue

            # A point is either [x, y, z] (written before support types
            # existed) or [x, y, z, "type"]. Both stay readable.
            types = beam.attributes.get("support_types") or {}
            for index, support_point in enumerate(support_points):
                if len(support_point) > 3:
                    support_type = str(support_point[3])
                else:
                    support_type = types.get(str(index)) or types.get(index) or "pinned"
                matched = False
                for node in (u, v):
                    node_point = structural_graph.node_point(node)
                    dx = node_point.x - support_point[0]
                    dy = node_point.y - support_point[1]
                    dz = node_point.z - support_point[2]
                    if (dx * dx + dy * dy + dz * dz) ** 0.5 <= tol:
                        by_type.setdefault(support_type, set()).add(node_to_id(structural_graph, node))
                        matched = True
                if not matched:
                    unmatched += 1

        if unmatched:
            self.report.append(f"{unmatched} declared support point(s) matched no structural node and were ignored")

        return by_type

    def _add_sections_and_members(self, model, structural_graph):
        for n1, n2 in structural_graph.beam_edges:
            segment: StructuralSegment = structural_graph.segment(n1, n2)
            assert segment.cross_section

            w, h = (value * self.scale for value in segment.cross_section)
            shape = "rectangular"
            # The grade travels with the beam, so a C24 joist and a GL24h
            # beam of the same size stay two sections.
            material_id = self._material_id_for(model, structural_graph.beam(n1, n2))
            section = self.sections_library.get_or_create_section(w, h, shape, material_id=material_id)

            problem = check_section_plausible(w, h, units=self.source_units)
            if problem and problem not in self.report:
                self.report.append(problem)

            # Wir geben den vollen Orientierungs-Vektor (Y-Achse) ans neutrale Modell weiter
            # Das ist 100% agnostisch!
            y_vector = Vector(*segment.frame.yaxis)

            beam = structural_graph.beam(n1, n2)
            # A beam is split into several members at joints and supports, so
            # the identity is the beam plus which piece of it this is. The
            # piece is named by its two endpoints - geometry, not graph order,
            # so it survives the beam's neighbours changing.
            start_id = node_to_id(structural_graph, n1)
            end_id = node_to_id(structural_graph, n2)
            segment_key = "{}:{}".format(*sorted((start_id, end_id)))
            release_start, release_end = self._beam_end_releases(structural_graph, beam, n1, n2)
            set_key = (getattr(beam, "attributes", {}) or {}).get("member_set") or source_id(beam)
            model.members.append(
                StructuralMember(
                    id=self._next_member_id(source_id(beam), segment_key),
                    node_start=start_id,
                    node_end=end_id,
                    section_id=section.id,
                    orientation_vector=y_vector,
                    release_start=release_start,
                    release_end=release_end,
                    source_element_id=source_id(beam),
                    source_element_type="beam",
                    source_segment_id=f"{source_id(beam)}:{segment_key}",
                )
            )
            self._set_keys.setdefault(set_key, []).append(model.members[-1].id)

    def _add_member_sets(self, model):
        """One member set per physical member that the analysis split into several.

        The members of a beam - or of every beam sharing ``attributes["member_set"]``
        (a girder modelled in pieces) - form one set: "continuous" when they
        chain end to end, else "group". Single members get none, as in an
        engineer's model. Ids follow the key, so a set keeps its id across runs.
        """
        if not self._set_keys:
            return
        by_id = {m.id: m for m in model.members}
        made = {"continuous": 0, "group": 0}
        for key, member_ids in sorted(self._set_keys.items(), key=lambda kv: str(kv[0])):
            members = [by_id[i] for i in member_ids if i in by_id]  # zero-length ones are gone
            if len(members) < 2:
                continue
            ordered = _chain(members)
            set_type = "continuous" if ordered is not None else "group"
            made[set_type] += 1
            model.member_sets.append(StructuralMemberSet(
                id=_unique_id(self._set_ids, "member_set", str(key)),
                name=str(key),
                member_ids=[m.id for m in (ordered or members)],
                set_type=set_type,
                source_element_id=str(key),
            ))
        if made["continuous"] or made["group"]:
            self.report.append("member sets: {} continuous, {} group".format(made["continuous"], made["group"]))

    #: How close (source units) a graph node must lie to a beam's centreline end
    #: to count as that end.
    END_TOLERANCE = 1e-6

    def _beam_end_releases(self, structural_graph, beam, n1, n2):
        """End releases a beam asks for, on the segment ends that are its own ends.

        ``beam.attributes["end_releases"]`` names them: a preset name for both
        ends ("pinned", "spherical", "rigid"), or ``{"start": ..., "end": ...}``
        with a preset name, a :class:`MemberRelease` or ``None`` per end. A
        beam split into several members gets the release only where its own
        centreline starts or ends - an engineer's member hinge, as on a column
        hinged top and bottom. Joints between system lines that do not meet
        are the joint policy's business (connectors), not this.
        """
        spec = getattr(beam, "attributes", {}).get("end_releases") if beam is not None else None
        if not spec:
            return None, None
        if not isinstance(spec, dict):
            spec = {"start": spec, "end": spec}
        line = beam.centerline
        tol = self.END_TOLERANCE / self.scale  # 1 micrometre, in source units

        def release_at(node):
            p = structural_graph.node_point(node)
            for end, q in (("start", line.start), ("end", line.end)):
                if p.distance_to_point(q) <= tol:
                    return _release_from(spec.get(end))
            return None

        return release_at(n1), release_at(n2)

    def _settle_fully_released_nodes(self, model):
        """Keep one member end continuous where every member end at a node is released.

        A node whose every member end is hinged has no rotational stiffness of
        its own: unless a support holds its rotations it is singular (OpenSees
        stops; RFEM eliminates it silently). Hinges on n-1 of the n ends are
        the same mechanics, so the release on one end - the lowest member id,
        deterministic - is dropped and recorded.
        """
        held = set()  # nodes a support holds against every rotation: hinges there are fine
        for support in model.supports:
            if all(getattr(support, dof) == float("inf") for dof in ("rx", "ry", "rz")):
                held.update(support.nodes)
        ends = {}
        for member in model.members:
            for node, attr in ((member.node_start, "release_start"), (member.node_end, "release_end")):
                ends.setdefault(node, []).append((member, attr))
        settled = 0
        for node, items in ends.items():
            if node in held:
                continue
            released = [(m, a) for m, a in items if getattr(m, a) is not None and not getattr(m, a).is_rigid()]
            if released and len(released) == len(items):
                member, attr = min(released, key=lambda item: str(item[0].id))
                setattr(member, attr, None)
                settled += 1
        if settled:
            self.report.append(
                "{} node(s) where every member end was hinged: one end kept continuous each "
                "(n-1 hinges, the same mechanics, no singular node)".format(settled))

    def _add_connectors(self, model, structural_graph):
        """Turn connector edges into members whose end conditions the joint policy decides.

        A connector edge stands for a real timber joint between two members
        whose system lines do not meet. Its mechanical behaviour - continuous,
        hinged, or springy - is the joint's, so the originating joint is read
        from the graph and passed through the policy.
        """
        rigid_section = self.sections_library.create_section("Rigid", 0, 0, "rectangular", material_id=1)
        decisions = {}
        beam_ends = self._beam_end_nodes(structural_graph)

        for n1, n2 in structural_graph.connector_edges:
            joint = structural_graph.joint(n1, n2)
            release = self.joint_policy.release_for(joint)

            description = self.joint_policy.describe_for(joint)
            decisions[description] = decisions.get(description, 0) + 1

            # A hinge sits on ONE end only. The connector spans from one
            # system line to the other; the real joint face is at the beam
            # that terminates there (butt joints), while the lever arm to the
            # continuous beam's axis is solid timber. Hinges at both ends would
            # make the connector a pendulum bar that carries axial force only,
            # and a beam hanging on parallel pendulum bars is a mechanism.
            # When both or neither beam ends here (corner, crossing lap), the
            # side is arbitrary and the second node takes the hinge.
            is_rigid = release.is_rigid()
            hinge_at_start = n1 in beam_ends and n2 not in beam_ends
            # A connector has no source element of its own - it exists because
            # two system lines do not meet. The pair of points it spans is what
            # identifies it.
            start_id = node_to_id(structural_graph, n1)
            end_id = node_to_id(structural_graph, n2)
            segment_key = "{}:{}".format(*sorted((start_id, end_id)))
            model.members.append(
                StructuralMember(
                    id=self._next_member_id("connector", segment_key),
                    node_start=start_id,
                    node_end=end_id,
                    section_id=rigid_section.id,
                    is_rigid=is_rigid,
                    member_type="RIGID" if is_rigid else "COUPLING",
                    release_start=release if not is_rigid and hinge_at_start else None,
                    release_end=release if not is_rigid and not hinge_at_start else None,
                    source_element_type="connector",
                    source_segment_id=f"connector:{segment_key}",
                    source_joint_start=source_id(joint) if joint is not None else None,
                    source_joint_end=source_id(joint) if joint is not None else None,
                )
            )

        for description, count in sorted(decisions.items()):
            self.report.append(f"{count}x {description}")

    @staticmethod
    def _beam_end_nodes(structural_graph):
        """Graph nodes at which some beam's system line terminates.

        A beam contributes one segment edge to each of its interior nodes'
        neighbours on both sides, so a node touched by exactly one segment of a
        beam is that beam's end. Nodes shared by two beams meeting end-to-end
        (mitres, butts on the axis) count as ends of both.
        """
        count = {}
        for u, v in structural_graph.beam_edges:
            beam = structural_graph.beam(u, v)
            key = source_id(beam)
            for node in (u, v):
                count[(node, key)] = count.get((node, key), 0) + 1
        return {node for (node, _key), n in count.items() if n == 1}

    def _add_nodes(self, model, structural_graph):
        for node in structural_graph.nodes():
            point = self._scaled_point(structural_graph.node_point(node))
            model.nodes.append(StructuralNode(id=node_to_id(structural_graph, node), point=point, source_node_id=source_id(node)))

    def _find_or_create_node(self, model, point, tol=1e-3):
        for n in model.nodes:
            if n.point.distance_to_point(point) < tol:
                return n.id
        new_id = max((n.id for n in model.nodes), default=0) + 1
        model.nodes.append(StructuralNode(id=new_id, point=point))
        return new_id

    def _mid_surface_offset(self, plate):
        """Vector from outline_a to the mid-surface, in source units.

        Derived from the two outlines rather than from the frame normal: a
        plate may be built either way round, and the outlines are what the
        analysis surface was derived from.
        """
        outline_a = getattr(plate, "outline_a", None)
        outline_b = getattr(plate, "outline_b", None)
        if not outline_a or not outline_b:
            return (0.0, 0.0, 0.0)
        try:
            a, b = outline_a[0], outline_b[0]
            return ((b[0] - a[0]) / 2.0, (b[1] - a[1]) / 2.0, (b[2] - a[2]) / 2.0)
        except (TypeError, IndexError):
            return (0.0, 0.0, 0.0)

    def _opening_rings(self, model, plate):
        """Openings of a plate as closed rings of node ids.

        Openings are `FreeContour` features on the plate. A plate carries one
        such feature for its outer contour too, and the two are told apart by
        `counter_sink` - compas_timber sets it from `interior`, false for the
        outline and true for every opening. That is a fabrication property
        doing double duty as topology, so it is worth naming here rather than
        leaving as a magic value in the middle of a loop.

        The ring vertices become model nodes like any other: an opening edge
        is a real boundary that a mesher has to honour and that a neighbouring
        plate could one day share. Points that coincide with existing nodes
        are reused, so an opening touching the outline stays connected.
        """
        if plate is None:
            return []
        openings = []
        for feature in getattr(plate, "features", None) or []:
            counter_sink = getattr(feature, "counter_sink", None)
            if counter_sink is None:
                # No flag on this feature - fall back to the cutter side.
                if getattr(feature, "tool_position", None) != OPENING_TOOL_POSITION:
                    continue
            elif bool(counter_sink) != OPENING_COUNTER_SINK:
                continue
            contour = getattr(feature, "contour_param_object", None)
            polyline = getattr(contour, "polyline", None)
            if polyline is not None:
                openings.append(polyline)

        # The contours lie on outline_a, the analysis surface is the middle
        # one - the plate study calls this out (no mid-plane is stored, it has
        # to be derived by t/2). Without the shift the opening sits half a
        # thickness off the surface it is supposed to cut, and gmsh either
        # ignores it or fails.
        offset = self._mid_surface_offset(plate)

        rings = []
        for opening in openings:
            ring = []
            seen = []
            for point in opening:
                shifted = Point(point[0] + offset[0], point[1] + offset[1], point[2] + offset[2])
                scaled = self._scaled_point(shifted)
                # A closed polyline repeats its first point; one node is enough.
                if seen and scaled.distance_to_point(seen[-1]) < 1e-9:
                    continue
                if seen and scaled.distance_to_point(seen[0]) < 1e-9:
                    continue
                seen.append(scaled)
                ring.append(self._find_or_create_node(model, scaled))
            if len(ring) < 3:
                self.report.append(
                    "plate {}: an opening with fewer than 3 distinct vertices was ignored".format(
                        source_id(plate)))
                continue
            rings.append(ring)
        if rings:
            self.report.append("{} opening(s) carried over from plate {}".format(
                len(rings), source_id(plate)))
        return rings

    def _add_plate_surfaces(self, model, structural_graph):
        surface_id_counter = 1
        for surface_data in structural_graph.surfaces:
            surface = surface_data["surface"]
            boundary_nodes = surface_data["boundary_nodes"]
            
            # Map structural_graph node keys to sequential IDs
            node_ids = [node_to_id(structural_graph, n) for n in boundary_nodes]
            
            thickness_value = surface.thickness * self.scale
            material_id = self._material_id_for(model, surface_data.get("plate") or surface)
            thickness_obj = self.thicknesses_library.get_or_create_thickness(
                thickness_value, material_id=material_id)

            problem = check_thickness_plausible(thickness_value, units=self.source_units)
            if problem and problem not in self.report:
                self.report.append(problem)
            
            # The analytical surface is regenerated on every translation, so its
            # guid is not stable. Results must map back to the source plate.
            parent_plate = getattr(surface, "parent_plate", None)

            model.surfaces.append(
                StructuralSurface(
                    id=surface_id_counter,
                    nodes=node_ids,
                    openings=self._opening_rings(model, parent_plate),
                    thickness_id=thickness_obj.id,
                    span_direction=self._span_direction(surface),
                    source_element_id=source_id(parent_plate) if parent_plate is not None else None,
                    source_element_type="plate",
                    source_surface_id=source_id(surface),
                )
            )
            surface_id_counter += 1

    def _span_direction(self, surface):
        """Local x axis of the plate, taken as its strong direction.

        Timber panels are markedly stiffer along the grain of their face layers,
        and an orthotropic surface needs a reference direction. compas_timber
        carries no layup, so this is the panel's geometric main axis rather than
        a measured grain direction - enough to orient an orthotropic material
        once the layup is known, and harmless while surfaces stay isotropic.
        """
        frame = getattr(surface, "frame", None)
        if frame is None:
            return None
        return Vector(*frame.xaxis)

    def _add_plate_connections(self, model, structural_graph):
        """Record where one plate meets another along an edge.

        Each connection edge is an edge of one plate's surface that abuts a
        neighbouring plate; the graph names both sides. Without such a
        connection the plates share no nodes and the model falls apart, so the
        connection carries the mechanical behaviour the plate policy assigns.
        """
        conn_id_counter = 1
        decisions = {}

        for n1, n2 in structural_graph.surface_connection_edges:
            attributes = structural_graph.edge_attributes((n1, n2))
            own_plate = attributes.get("plate") if hasattr(attributes, "get") else None
            # A connection line's parent plate is the plate on the other side
            # of the joint; an edge can carry several lines, one per neighbour.
            plates = [own_plate] + [
                line.parent_plate for line in structural_graph.surface_lines(n1, n2) if line.line_type == "connection"
            ]
            source_element_ids = []
            for plate in plates:
                if plate is not None and source_id(plate) not in source_element_ids:
                    source_element_ids.append(source_id(plate))

            joint = structural_graph.joint(n1, n2)
            release = self.plate_policy.release_for(joint)

            kind = "rigid" if release.is_rigid() else "released " + "/".join(release.released_dofs())
            basis = "joint rule" if joint is not None else "policy default (plate connectors carry no joint reference)"
            decisions[f"plate edge: {kind} ({basis})"] = decisions.get(f"plate edge: {kind} ({basis})", 0) + 1

            model.surface_connections.append(
                StructuralSurfaceConnection(
                    id=conn_id_counter,
                    nodes=[node_to_id(structural_graph, n1), node_to_id(structural_graph, n2)],
                    release=release,
                    source_joint_id=source_id(joint) if joint is not None else None,
                    source_element_ids=source_element_ids,
                )
            )
            conn_id_counter += 1

        for description, count in sorted(decisions.items()):
            self.report.append(f"{count}x {description}")

    def _add_support_nodes(self, model, structural_graph):
        """Turn the authored support points into supports, one per type.

        `Tekton Support` writes a type alongside each point; points that
        share a type share a support object, which is how an engineer reads
        it ("the roller line") and how RFEM groups them. Points written
        before the type existed carry none and become pinned - the old
        behaviour, kept so existing models translate unchanged.
        """
        from tekton_core.core.support_types import stiffnesses

        by_type = self._get_support_nodes(model, structural_graph)
        for index, (support_type, node_ids) in enumerate(sorted(by_type.items()), start=1):
            if not node_ids:
                continue
            try:
                dofs = stiffnesses(support_type)
            except ValueError as error:
                self.report.append(
                    "{} Falling back to pinned for {} node(s).".format(error, len(node_ids)))
                dofs = stiffnesses("pinned")
                support_type = "pinned"
            model.supports.append(
                StructuralSupport(
                    id=index,
                    nodes=sorted(node_ids),
                    name="Designated {} support".format(support_type.replace("_", " ")),
                    **dofs
                )
            )

    def _add_line_supports(self, model, timber_model):
        """Turn supported plate edges into line supports.

        Two ways to declare one, because they fail differently:

        * ``supported_edges`` - a list of edge indices on the plate. Exact,
          survives remeshing, and is what an edge *is* in the plate's own
          representation.
        * ``support_lines`` - curves, matched against plate edges by
          tolerance. The familiar Grasshopper gesture, and the same
          machinery as the support points, with the same failure mode: a
          line that matches nothing is reported rather than silently lost.

        Both end up as a chain of node ids on the surface outline, which is
        what makes the support conform to the mesh by construction.
        """
        from tekton_core.core.support_types import stiffnesses

        plates = list(getattr(timber_model, "plates", None) or [])
        if not plates:
            return

        surfaces_by_source = {}
        for surface in model.surfaces:
            if surface.source_element_id:
                surfaces_by_source.setdefault(str(surface.source_element_id), []).append(surface)

        points = {node.id: node.point for node in model.nodes}
        next_id = 1
        unmatched = 0

        for plate in plates:
            attributes = getattr(plate, "attributes", None) or {}
            declared = self._declared_edges(plate, attributes)
            if not declared:
                continue

            for surface in surfaces_by_source.get(str(plate.guid), []):
                ring = surface.nodes or []
                for edge_index, support_type in sorted(declared.items()):
                    if edge_index >= len(ring):
                        unmatched += 1
                        continue
                    chain = [ring[edge_index], ring[(edge_index + 1) % len(ring)]]
                    if any(n not in points for n in chain):
                        unmatched += 1
                        continue
                    if points[chain[0]].distance_to_point(points[chain[1]]) < 1e-9:
                        # A degenerate edge has no length for a per-metre
                        # stiffness to act over.
                        unmatched += 1
                        continue
                    try:
                        dofs = stiffnesses(support_type)
                    except ValueError as error:
                        self.report.append(
                            "{} Falling back to pinned for a plate edge.".format(error))
                        dofs = stiffnesses("pinned")
                        support_type = "pinned"
                    model.line_supports.append(
                        StructuralLineSupport(
                            id=next_id,
                            nodes=chain,
                            name="Supported edge ({})".format(support_type.replace("_", " ")),
                            source_element_id=str(plate.guid),
                            source_edge_index=edge_index,
                            **dofs
                        )
                    )
                    next_id += 1

        if unmatched:
            self.report.append(
                "{} declared plate edge(s) matched no surface edge and were ignored".format(unmatched))
        if model.line_supports:
            self.report.append("{} line support(s) from supported plate edges".format(len(model.line_supports)))

    def _declared_edges(self, plate, attributes):
        """{edge index: support type} from either way of declaring it."""
        declared = {}

        # by index - exact
        for entry in attributes.get("supported_edges") or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                declared[int(entry[0])] = str(entry[1])
            else:
                declared[int(entry)] = "pinned"

        # by curve - matched against the plate's own outline
        lines = attributes.get("support_lines") or []
        if lines:
            declared.update(self._edges_near(plate, lines))
        return declared

    def _edges_near(self, plate, lines, tol=1e-3):
        """Match declared curves onto plate edge indices by midpoint."""
        outline = getattr(plate, "outline_a", None)
        if outline is None:
            return {}
        corners = list(outline)
        found = {}
        for line in lines:
            support_type = "pinned"
            if isinstance(line, (list, tuple)) and len(line) == 3 and not hasattr(line[0], "__len__"):
                continue
            try:
                start, end = line[0], line[1]
                if len(line) > 2 and isinstance(line[2], str):
                    support_type = line[2]
            except (TypeError, IndexError):
                continue
            mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0, (start[2] + end[2]) / 2.0)
            for index in range(len(corners) - 1):
                a, b = corners[index], corners[index + 1]
                edge_mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
                distance = sum((mid[i] - edge_mid[i]) ** 2 for i in range(3)) ** 0.5
                if distance < tol:
                    found[index] = support_type
                    break
        return found
