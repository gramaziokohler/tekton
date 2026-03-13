from compas.geometry import Vector
from compas_timber.structural import SimpleBeamSegmentGenerator
from .core.model import StructuralModel, StructuralNode, StructuralMember, StructuralSupport, StructuralSection
from .utils import NodeManager

class FixedSimpleBeamSegmentGenerator(SimpleBeamSegmentGenerator):
    """Temporary fix for inconsistencies in structural.py"""
    def generate_segments(self, beam, joints):
        # We RE-IMPLEMENT _create_segments here because the one in structural.py 
        # uses 'segment=' instead of 'line=' which fails the constructor.
        from compas.geometry import Frame, distance_point_point, intersection_segment_segment, closest_point_on_segment, Point, Line
        from compas.itertools import pairwise
        from compas.tolerance import TOL
        from compas_timber.structural import StructuralSegment

        split_points_with_distances = []
        for joint in joints:
            for other_element in joint.elements:
                if other_element is beam:
                    continue
                try:
                    p1, p2 = intersection_segment_segment(beam.centerline, other_element.centerline)
                except:
                    p1 = None
                
                if p1 is not None:
                    point_on_segment = Point(*p1)
                else:
                    point_on_segment = Point(*closest_point_on_segment(joint.location, beam.centerline))

                dist = distance_point_point(beam.centerline.start, point_on_segment)
                if not (TOL.is_zero(dist) or TOL.is_zero(dist - beam.length)):
                    if not any(TOL.is_zero(abs(dp[0] - dist)) for dp in split_points_with_distances):
                        split_points_with_distances.append((dist, point_on_segment))

        split_points_with_distances.sort(key=lambda x: x[0])
        pts = [v[1] for v in split_points_with_distances]
        
        segments = []
        for p1, p2 in pairwise([beam.centerline.start] + pts + [beam.centerline.end]):
            line = Line(p1, p2)
            # FIX: Use 'line=' instead of 'segment=' to match StructuralSegment.__init__
            segments.append(StructuralSegment(line=line, frame=Frame(line.start, beam.frame.xaxis, beam.frame.yaxis)))
        return segments

class TimberToStructural:
    """Konvertiert ein compas_timber Model in ein neutrales StructuralModel"""
    def __init__(self, connector_mode="rigid", material_name="C24"):
        self.connector_mode = connector_mode
        self.node_manager = NodeManager()
        self.material_name = material_name

    def translate(self, timber_model) -> StructuralModel:
        # Sicherstellen, dass die strukturellen Segmente generiert sind
        if not any(timber_model.get_beam_structural_segments(beam) for beam in timber_model.beams):
            print("Generiere strukturelle Segmente...")
            # We inject our fixed generator because structural.py has a bug (missing abstract method implementation)
            from compas_timber.structural import BeamStructuralElementSolver
            solver = BeamStructuralElementSolver(beam_segment_generator=FixedSimpleBeamSegmentGenerator())
            timber_model.create_beam_structural_segments(solver=solver)

        model = StructuralModel()
        model.materials[1] = self.material_name
        
        member_id_counter = 1
        section_id_counter = 1
        sections_map = {} # (width, height, shape) -> section_id
        
        # 1. Beams
        for beam in timber_model.beams:
            segments = timber_model.get_beam_structural_segments(beam)
            
            # Querschnitt finden oder anlegen (Agnostisch über Geometrie)
            # Beam dimensions in raw data are in meters (0.08, 0.1 etc)
            w = float(beam.width)
            h = float(beam.height)
            shape = "rectangular"
            key = (w, h, shape)
            
            if key not in sections_map:
                sec_id = section_id_counter
                # Dlubal-kompatibler Name für rechteckige Holz-Querschnitte
                # Breite/Höhe in mm konvertieren
                w_mm = int(w * 1000)
                h_mm = int(h * 1000)
                
                # Check if values are logically too large (if user meant it was 80/100, then 80000/100000 is wrong)
                # But since raw data is 0.08, w_mm = 80. This is correct.
                # However, if Dlubal expects meters or if the importer-old used different logic, let's re-verify.
                name = f"R_M1 {w}/{h}"
                
                model.sections.append(StructuralSection(
                    id=sec_id, 
                    name=name, 
                    width=w, 
                    height=h, 
                    shape_type=shape,
                    material_id=1
                ))
                sections_map[key] = sec_id
                section_id_counter += 1
            
            current_section_id = sections_map[key]

            for segment in segments:
                # Use 'line' from StructuralSegment as confirmed in structural.py
                geometry = segment.line
                if not geometry:
                    raise AttributeError(f"StructuralSegment has no 'line' attribute: {dir(segment)}")

                n1 = self.node_manager.get_node_number(geometry.start)
                n2 = self.node_manager.get_node_number(geometry.end)
                
                # Wir geben den vollen Orientierungs-Vektor (Y-Achse) ans neutrale Modell weiter
                # Das ist 100% agnostisch!
                y_vector = Vector(*segment.frame.yaxis)
                
                model.members.append(StructuralMember(
                    id=member_id_counter,
                    node_start=n1,
                    node_end=n2,
                    section_id=current_section_id,
                    orientation_vector=y_vector
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
                    geometry = segment.line
                    if not geometry:
                         continue

                    n1 = self.node_manager.get_node_number(geometry.start)       
                    n2 = self.node_manager.get_node_number(geometry.end)
                    
                    # Bestimme den Typ basierend auf connector_mode
                    m_type = "RIGID" if self.connector_mode == "rigid" else "COUPLING"

                    model.members.append(StructuralMember(
                        id=member_id_counter,
                        node_start=n1,
                        node_end=n2,
                        section_id=rigid_sec_id,
                        is_rigid=(m_type == "RIGID"),
                        member_type=m_type
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
            # Standardmäßig Pinned Support (Rotation frei, Bewegung gesperrt)
            # inf = gesperrt, 0.0 = frei
            model.supports.append(StructuralSupport(
                id=1, 
                nodes=base_nodes, 
                name="Auto Pinned Support",
                ux=float('inf'), # X gesperrt
                uy=float('inf'), # Y gesperrt
                uz=float('inf'), # Z gesperrt
                rx=0.0,          # Rotation X frei
                ry=0.0,          # Rotation Y frei
                rz=0.0           # Rotation Z frei
            ))

        # 4. Loads (Static Cases - Default for now)
        from ct_dlubal.core.model import StructuralLoadCase, StructuralPointLoad
        model.load_cases.append(StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True))

        return model
