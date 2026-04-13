from compas.geometry import Vector
from compas_timber.structural import StructuralSegment
from compas_timber.structural import StructuralGraph
from compas_timber.structural import BeamStructuralElementSolver

from compas_timber_fea.core.model import StructuralLoadCase

from .core.model import StructuralMember
from .core.model import StructuralModel
from .core.model import StructuralNode
from .core.model import StructuralSection
from .core.model import StructuralSupport
from .utils import NodeManager


class SectionLibrary:
    """Will keep track of created sections to avoid duplicates. Sections are defined by their dimensions and shape type."""

    def __init__(self):
        self.model_sections = None
        self.sections_map = {}
        self._section_id_counter = 1

    def create_section(self, name, width, height, shape, material_id):
        key = (width, height, shape)
        if key in self.sections_map:
            raise ValueError(f"Section with dimensions {width}x{height} and shape {shape} already exists.")
        sec_id = self._section_id_counter

        section = StructuralSection(id=sec_id, name=name, width=width, height=height, shape_type=shape, material_id=material_id)
        self.model_sections.append(section)
        self.sections_map[(width, height, shape)] = section
        self._section_id_counter += 1
        return section

    def get_or_create_section(self, width, height, shape, material_id):
        key = (width, height, shape)
        if key not in self.sections_map:
            name = f"R_M1 {width}/{height}"
            self.create_section(name, width, height, shape, material_id)
        return self.sections_map[key]


def node_to_id(sg, node):
    # dlubal apparantly doesn't do zero-based ids
    # use stable node indices from the graph
    return sg.node_index(node) + 1

class TimberToStructural:
    """Konvertiert ein compas_timber Model in ein neutrales StructuralModel"""

    def __init__(self, connector_mode="rigid", material_name="C24"):
        self.connector_mode = connector_mode
        self.material_name = material_name
        self.sections_library = SectionLibrary()
        self._member_id_counter = 1

    def translate(self, timber_model) -> StructuralModel:
        # Sicherstellen, dass die strukturellen Segmente generiert sind
        if not any(timber_model.get_beam_structural_segments(beam) for beam in timber_model.beams):
            print("Generiere strukturelle Segmente...")
            timber_model.create_beam_structural_segments()

        model = StructuralModel()
        self.sections_library.model_sections = model.sections  # Damit die SectionLibrary direkt in das Model schreibt
        model.materials[1] = self.material_name

        solver = BeamStructuralElementSolver()
        _, joints_traversed = solver.add_structural_segments(timber_model)
        solver.add_joint_structural_segments(timber_model, joints_traversed)
        structural_graph = StructuralGraph.from_model(timber_model)

        self._add_sections_and_members(model, structural_graph)
        # Wir brauchen ein "Rigid" Section für virtuelle Stäbe
        self._add_connectors(model, structural_graph)
        # 2. Joints (Connectors)
        self._add_nodes(model, structural_graph)

        # Heuristik für Lager: Alle Nodes bei Z~0 bekommen ein Lager (ID 1)
        self._add_support_nodes(model)

        # 4. Loads (Static Cases - Default for now)
        self._add_load_cases(model)
        return model

    def _add_load_cases(self, model):
        model.load_cases.append(StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True))

    def _get_support_nodes(self, model):
        # Heuristik: Alle Nodes mit Z ~ 0 bekommen ein Lager
        return [n.id for n in model.nodes if abs(n.point.z) <= 0.01]

    def _add_sections_and_members(self, model, structural_graph):
        for n1, n2 in structural_graph.beam_edges:
            segment: StructuralSegment = structural_graph.segment(n1, n2)
            assert segment.cross_section

            w, h = segment.cross_section
            shape = "rectangular"
            section = self.sections_library.get_or_create_section(w, h, shape, material_id=1)

            # Wir geben den vollen Orientierungs-Vektor (Y-Achse) ans neutrale Modell weiter
            # Das ist 100% agnostisch!
            y_vector = Vector(*segment.frame.yaxis)

            model.members.append(StructuralMember(id=self._member_id_counter, node_start=node_to_id(structural_graph, n1), node_end=node_to_id(structural_graph, n2), section_id=section.id, orientation_vector=y_vector))
            self._member_id_counter += 1

    def _add_connectors(self, model, structural_graph):
        rigid_section = self.sections_library.create_section("Rigid", 0, 0, "rectangular", material_id=1)

        for n1, n2 in structural_graph.connector_edges:
            # Bestimme den Typ basierend auf connector_mode
            m_type = "RIGID" if self.connector_mode == "rigid" else "COUPLING"

            model.members.append(
                StructuralMember(id=self._member_id_counter, node_start=node_to_id(structural_graph, n1), node_end=node_to_id(structural_graph, n2), section_id=rigid_section.id, is_rigid=(m_type == "RIGID"), member_type=m_type)
            )
            self._member_id_counter += 1  # TODO: this could be more neatly handled by the StructuralModel class itself.

    def _add_nodes(self, model, structural_graph):
        for node in structural_graph.nodes():
            point = structural_graph.node_point(node)
            model.nodes.append(StructuralNode(id=node_to_id(structural_graph, node), point=point))

    def _add_support_nodes(self, model):
        base_nodes = self._get_support_nodes(model)
        if base_nodes:
            # Standardmäßig Pinned Support (Rotation frei, Bewegung gesperrt)
            # inf = gesperrt, 0.0 = frei
            model.supports.append(
                StructuralSupport(
                    id=1,
                    nodes=base_nodes,
                    name="Auto Pinned Support",
                    ux=float("inf"),  # X gesperrt
                    uy=float("inf"),  # Y gesperrt
                    uz=float("inf"),  # Z gesperrt
                    rx=0.0,  # Rotation X frei
                    ry=0.0,  # Rotation Y frei
                    rz=0.0,  # Rotation Z frei
                )
            )
