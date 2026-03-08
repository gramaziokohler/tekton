import math
from compas.geometry import Vector
from ..core.model import StructuralMember, StructuralSection

class MemberMapper:
    """Konvertiert neutrale Member/Sections in Dlubal PB Objekte"""
    def __init__(self, Core):
        self.Core = Core

    def map_section(self, section: StructuralSection):
        if section.name == "Rigid":
            name = "Rigid"
        elif section.shape_type == "rectangular":
            w_mm = int(section.width * 1000)
            h_mm = int(section.height * 1000)
            name = f"R_M1 {w_mm}/{h_mm}"
        else:
            name = section.name
        
        return self.Core.CrossSection(
            no=section.id,
            name=name,
            material=section.material_id
        )

    def map_member(self, member: StructuralMember):
        if member.is_rigid:
            # TYPE_RIGID = 2
            return self.Core.Member(
                no=member.id,
                type=2,
                node_start=member.node_start,
                node_end=member.node_end
            )
        
        return self.Core.Member(
            no=member.id,
            node_start=member.node_start,
            node_end=member.node_end,
            cross_section_start=member.section_id,
            cross_section_end=member.section_id,
            is_rotated=bool(member.rotation != 0.0),
            rotation_specification_type=0, # BY_ANGLE
            rotation_angle=float(member.rotation)
        )

    def map_material(self, mat_id: int, mat_name: str):
        desc = self.Core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type
        timber_type_id = desc.values_by_name['MATERIAL_TYPE_TIMBER'].number
        return self.Core.Material(
            no=mat_id,
            name=mat_name,
            material_type=timber_type_id
        )
