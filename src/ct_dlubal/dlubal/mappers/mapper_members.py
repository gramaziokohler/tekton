import math
from compas.geometry import Vector
from ...core.model import StructuralMember, StructuralSection, StructuralNode
from ..utils import calculate_beta_from_vector

class MemberMapper:
    """Konvertiert neutrale Member/Sections in Dlubal PB Objekte"""
    
    # Mapping for common timber materials (as in importer-old.py)
    MATERIAL_LIBRARY = {
        "GL24h": "GL24h | EN 14080:2013-09",
        "GL24c": "GL24c | EN 14080:2013-09",
        "GL28c": "GL28c | EN 14080:2013-09",
        "GL30c": "GL30c | EN 14080:2013-09",
        "C14": "C14 | EN 338:2016-04",
        "C16": "C16 | EN 338:2016-04",
        "C24": "C24 | EN 338:2016-04",
        "C30": "C30 | EN 338:2016-04"
    }

    def __init__(self, Core, nodes_cache=None):
        self.Core = Core
        # Wir brauchen Zugriff auf die Knotenkoordinaten für die Winkelberechnung
        self.nodes_cache = nodes_cache or {} 

    # ... (map_section and map_material remain similar)

    def map_member(self, member: StructuralMember):
        if member.member_type == "RIGID":
            # Dlubal Type 2 is RIGID. 
            return self.Core.Member(
                no=member.id,
                type=2, # TYPE_RIGID
                node_start=member.node_start,
                node_end=member.node_end
            )
        
        if member.member_type == "COUPLING":
            # Dlubal Type 24 is COUPLING (hinged-hinged rigid link)
            # Useful for rotational stiffness/hinged connectors
            return self.Core.Member(
                no=member.id,
                type=24, # TYPE_COUPLING_HINGE_HINGE
                node_start=member.node_start,
                node_end=member.node_end
            )
        
        # Standard BEAM (Type 1 is default)
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
        
        # Resolve full name using library or use fallback
        full_name = self.MATERIAL_LIBRARY.get(mat_name, mat_name)
        
        return self.Core.Material(
            no=mat_id,
            name=full_name,
            material_type=timber_type_id
        )

    def map_section(self, section: StructuralSection):
        # In RSTAB heißt es CrossSection, in RFEM oft auch Section
        section_attr = getattr(self.Core, "CrossSection", getattr(self.Core, "Section", None))
        if not section_attr:
             raise AttributeError(f"Dlubal StructureCore has no CrossSection or Section: {dir(self.Core)}")

        # Protobuf Objekte akzeptieren oft nur die ID für verknüpfte Objekte
        return section_attr(
            no=section.id,
            name=section.name, 
            material=section.material_id # RSTAB nutzt 'material', RFEM 'material_no'
        )
