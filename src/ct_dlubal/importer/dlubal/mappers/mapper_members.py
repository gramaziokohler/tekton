import math
from compas.geometry import Vector
from ..core.model import StructuralMember, StructuralSection, StructuralNode
from .utils import calculate_beta_from_vector

class MemberMapper:
    """Konvertiert neutrale Member/Sections in Dlubal PB Objekte"""
    def __init__(self, Core, nodes_cache=None):
        self.Core = Core
        # Wir brauchen Zugriff auf die Knotenkoordinaten für die Winkelberechnung
        self.nodes_cache = nodes_cache or {} 

    # ... (map_section and map_material remain similar)

    def map_member(self, member: StructuralMember):
        if member.is_rigid:
            return self.Core.Member(
                no=member.id,
                type=2,
                node_start=member.node_start,
                node_end=member.node_end
            )
        
        # Beta Winkel on-the-fly im Mapper berechnen (Software-Spezifisch!)
        p1 = self.nodes_cache.get(member.node_start)
        p2 = self.nodes_cache.get(member.node_end)
        beta = 0.0
        if p1 and p2:
            beta = calculate_beta_from_vector(p1, p2, member.orientation_vector)

        return self.Core.Member(
            no=member.id,
            node_start=member.node_start,
            node_end=member.node_end,
            cross_section_start=member.section_id,
            cross_section_end=member.section_id,
            is_rotated=bool(beta != 0.0),
            rotation_specification_type=0, 
            rotation_angle=float(beta)
        )

    def map_material(self, mat_id: int, mat_name: str):
        desc = self.Core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type
        timber_type_id = desc.values_by_name['MATERIAL_TYPE_TIMBER'].number
        return self.Core.Material(
            no=mat_id,
            name=mat_name,
            material_type=timber_type_id
        )
