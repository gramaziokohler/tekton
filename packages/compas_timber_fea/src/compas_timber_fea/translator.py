import math

from compas.geometry import Point
from compas.geometry import Vector
from compas_timber.structural import StructuralSegment
from compas_timber.structural import StructuralGraph
from compas_timber.structural import BeamStructuralElementSolver

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.joint_policy import PlateConnectionPolicy
from compas_timber_fea.core.joint_policy import policy_from_connector_mode
from compas_timber_fea.core.materials import Material
from compas_timber_fea.core.units import check_section_plausible
from compas_timber_fea.core.units import check_thickness_plausible
from compas_timber_fea.core.units import scale_to_meters

from .core.model import StructuralMember
from .core.model import StructuralModel
from .core.model import StructuralNode
from .core.model import StructuralSection
from .core.model import StructuralSupport
from .core.model import StructuralThickness
from .core.model import StructuralSurface
from .core.model import StructuralSurfaceConnection


#: Dimensions closer than this (in metres) are treated as the same catalogue
#: entry. Geometry derived from CAD carries float noise well below a tenth of
#: a millimetre, which must not produce duplicate sections or thicknesses.
DIMENSION_TOLERANCE = 1e-5


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
        key = _dimension_key(width, height, shape)
        if key in self.sections_map:
            raise ValueError(f"Section with dimensions {width}x{height} and shape {shape} already exists.")
        sec_id = self._section_id_counter

        section = StructuralSection(id=sec_id, name=name, width=width, height=height, shape_type=shape, material_id=material_id)
        self.model_sections.append(section)
        self.sections_map[key] = section
        self._section_id_counter += 1
        return section

    def get_or_create_section(self, width, height, shape, material_id):
        key = _dimension_key(width, height, shape)
        if key not in self.sections_map:
            name = f"R_M1 {width}/{height}"
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


def node_to_id(sg, node):
    # dlubal apparantly doesn't do zero-based ids
    # use stable node indices from the graph
    return sg.node_index(node) + 1

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
        :mod:`compas_timber_fea.core.units`.
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
        self._member_id_counter = 1
        #: Assumptions and anomalies recorded during the last translate().
        self.report = []

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
            plate_solver = PlateStructuralElementSolver()
            plate_solver.add_structural_surfaces(timber_model)
            # Process all joints for plate-plate connections
            plate_joints = [j for j in timber_model.joints if any(hasattr(el, "outline_a") for el in j.elements)]
            plate_solver.add_joint_structural_lines(timber_model, plate_joints)

        structural_graph = StructuralGraph.from_model(timber_model)

        model = StructuralModel()
        model.source_units = self.source_units
        self.report = []
        self.sections_library.model_sections = model.sections  # Damit die SectionLibrary direkt in das Model schreibt
        self.thicknesses_library.model_thicknesses = model.thicknesses

        material = Material.resolve(self.material_name)
        model.materials[1] = material
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

        # Lager nur aus explizit markierten Support-Punkten im TimberModel ableiten.
        self._add_support_nodes(model, structural_graph)

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
        support_node_ids = set()
        unmatched = 0

        for u, v in structural_graph.beam_edges:
            beam = structural_graph.beam(u, v)
            support_points = beam.attributes.get("support_points", [])

            if not support_points:
                continue

            for support_point in support_points:
                matched = False
                for node in (u, v):
                    node_point = structural_graph.node_point(node)
                    dx = node_point.x - support_point[0]
                    dy = node_point.y - support_point[1]
                    dz = node_point.z - support_point[2]
                    if (dx * dx + dy * dy + dz * dz) ** 0.5 <= tol:
                        support_node_ids.add(node_to_id(structural_graph, node))
                        matched = True
                if not matched:
                    unmatched += 1

        if unmatched:
            self.report.append(f"{unmatched} declared support point(s) matched no structural node and were ignored")

        return sorted(support_node_ids)

    def _add_sections_and_members(self, model, structural_graph):
        for n1, n2 in structural_graph.beam_edges:
            segment: StructuralSegment = structural_graph.segment(n1, n2)
            assert segment.cross_section

            w, h = (value * self.scale for value in segment.cross_section)
            shape = "rectangular"
            section = self.sections_library.get_or_create_section(w, h, shape, material_id=1)

            problem = check_section_plausible(w, h, units=self.source_units)
            if problem and problem not in self.report:
                self.report.append(problem)

            # Wir geben den vollen Orientierungs-Vektor (Y-Achse) ans neutrale Modell weiter
            # Das ist 100% agnostisch!
            y_vector = Vector(*segment.frame.yaxis)

            beam = structural_graph.beam(n1, n2)
            model.members.append(
                StructuralMember(
                    id=self._member_id_counter,
                    node_start=node_to_id(structural_graph, n1),
                    node_end=node_to_id(structural_graph, n2),
                    section_id=section.id,
                    orientation_vector=y_vector,
                    source_element_id=source_id(beam),
                    source_element_type="beam",
                    source_segment_id=f"{source_id(beam)}:{source_id(n1)}-{source_id(n2)}",
                )
            )
            self._member_id_counter += 1

    def _add_connectors(self, model, structural_graph):
        """Turn connector edges into members whose end conditions the joint policy decides.

        A connector edge stands for a real timber joint between two members
        whose system lines do not meet. Its mechanical behaviour - continuous,
        hinged, or springy - is the joint's, so the originating joint is read
        from the graph and passed through the policy.
        """
        rigid_section = self.sections_library.create_section("Rigid", 0, 0, "rectangular", material_id=1)
        decisions = {}

        for n1, n2 in structural_graph.connector_edges:
            joint = structural_graph.joint(n1, n2)
            release = self.joint_policy.release_for(joint)

            description = self.joint_policy.describe_for(joint)
            decisions[description] = decisions.get(description, 0) + 1

            is_rigid = release.is_rigid()
            model.members.append(
                StructuralMember(
                    id=self._member_id_counter,
                    node_start=node_to_id(structural_graph, n1),
                    node_end=node_to_id(structural_graph, n2),
                    section_id=rigid_section.id,
                    is_rigid=is_rigid,
                    member_type="RIGID" if is_rigid else "COUPLING",
                    release_start=None if is_rigid else release,
                    release_end=None if is_rigid else release,
                    source_element_type="connector",
                    source_segment_id=f"{source_id(n1)}-{source_id(n2)}",
                    source_joint_start=source_id(joint) if joint is not None else None,
                    source_joint_end=source_id(joint) if joint is not None else None,
                )
            )
            self._member_id_counter += 1  # TODO: this could be more neatly handled by the StructuralModel class itself.

        for description, count in sorted(decisions.items()):
            self.report.append(f"{count}x {description}")

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

    def _add_plate_surfaces(self, model, structural_graph):
        surface_id_counter = 1
        for surface_data in structural_graph.surfaces:
            surface = surface_data["surface"]
            boundary_nodes = surface_data["boundary_nodes"]
            
            # Map structural_graph node keys to sequential IDs
            node_ids = [node_to_id(structural_graph, n) for n in boundary_nodes]
            
            thickness_value = surface.thickness * self.scale
            thickness_obj = self.thicknesses_library.get_or_create_thickness(thickness_value, material_id=1)

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
            line = attributes.get("line") if hasattr(attributes, "get") else None
            own_plate = attributes.get("plate") if hasattr(attributes, "get") else None
            # The line's parent plate is the plate on the other side of the joint.
            other_plate = getattr(line, "parent_plate", None)

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
                    source_element_ids=[
                        source_id(plate) for plate in (own_plate, other_plate) if plate is not None
                    ],
                )
            )
            conn_id_counter += 1

        for description, count in sorted(decisions.items()):
            self.report.append(f"{count}x {description}")

    def _add_support_nodes(self, model, structural_graph):
        base_nodes = self._get_support_nodes(model, structural_graph)
        if base_nodes:
            # Standardmäßig Pinned Support (Rotation frei, Bewegung gesperrt)
            # inf = gesperrt, 0.0 = frei
            model.supports.append(
                StructuralSupport(
                    id=1,
                    nodes=base_nodes,
                    name="Designated Pinned Support",
                    ux=float("inf"),  # X gesperrt
                    uy=float("inf"),  # Y gesperrt
                    uz=float("inf"),  # Z gesperrt
                    rx=0.0,  # Rotation X frei
                    ry=0.0,  # Rotation Y frei
                    rz=0.0,  # Rotation Z frei
                )
            )
