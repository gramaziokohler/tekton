from .core.model import StructuralModel, StructuralNode, StructuralMember, StructuralSupport, StructuralSection
from .utils import NodeManager, calculate_dlubal_rotation

class TimberToStructural:
    """Konvertiert ein compas_timber Model in ein neutrales StructuralModel"""
    def __init__(self, connector_mode="rigid", material_name="C24"):
        self.connector_mode = connector_mode
        self.node_manager = NodeManager()
        self.material_name = material_name

    def translate(self, timber_model) -> StructuralModel:
        model = StructuralModel()
        model.materials[1] = self.material_name
        
        member_id_counter = 1
        section_id_counter = 1
        sections_map = {} # timber dims -> section_id
        
        # 1. Beams
        for beam in timber_model.beams:
            segments = timber_model.get_beam_structural_segments(beam)
            
            # Querschnitt finden oder anlegen
            dims = (float(beam.width), float(beam.height))
            if dims not in sections_map:
                sec_id = section_id_counter
                section_name = f"R_M1 {dims[0]}/{dims[1]}"
                model.sections.append(StructuralSection(id=sec_id, name=section_name, material_id=1))
                sections_map[dims] = sec_id
                section_id_counter += 1
            
            current_section_id = sections_map[dims]

            for segment in segments:
                n1 = self.node_manager.get_node_number(segment.segment.start)
                n2 = self.node_manager.get_node_number(segment.segment.end)
                beta = calculate_dlubal_rotation(segment.frame)
                
                model.members.append(StructuralMember(
                    id=member_id_counter,
                    node_start=n1,
                    node_end=n2,
                    section_id=current_section_id,
                    rotation=beta
                ))
                member_id_counter += 1

        # 2. Joints (Connectors)
        # Wir brauchen ein "Rigid" Section für virtuelle Stäbe
        rigid_sec_id = section_id_counter
        model.sections.append(StructuralSection(id=rigid_sec_id, name="Rigid", material_id=1))

        for joint in timber_model.joints:
            if len(joint.elements) == 2:
                beam_a, beam_b = joint.elements
                for segment in timber_model.get_structural_connector_segments(beam_a, beam_b):
                    n1 = self.node_manager.get_node_number(segment.segment.start)       
                    n2 = self.node_manager.get_node_number(segment.segment.end)
                    
                    model.members.append(StructuralMember(
                        id=member_id_counter,
                        node_start=n1,
                        node_end=n2,
                        section_id=rigid_sec_id,
                        is_rigid=True
                    ))
                    member_id_counter += 1

        # 3. Nodes sammeln
        for node_id, pt in self.node_manager.nodes:
            model.nodes.append(StructuralNode(id=node_id, point=pt))
            
            # Automatische Basis-Lager (Z=0 Logik)
            if abs(pt.z) <= 0.01:
                # Wir fügen hier einfach ein Lager hinzu, wenn wir Nodes identifizieren
                # (Einfache Heuristik für den Anfang)
                pass
        
        # Heuristik für Lager: Alle Nodes bei Z~0 bekommen ein Lager (ID 1)
        base_nodes = [n.id for n in model.nodes if abs(n.point.z) <= 0.01]
        if base_nodes:
            model.supports.append(StructuralSupport(id=1, nodes=base_nodes, name="Auto Base Support"))

        return model
