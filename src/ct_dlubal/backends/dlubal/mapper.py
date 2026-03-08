import math
from ...core.model import StructuralModel, StructuralNode, StructuralMember, StructuralSupport

class DlubalMapper:
    """Übersetzt das neutrale StructuralModel in Dlubal API Objekte (Protobuf)"""
    def __init__(self, Core, TFN, Loc, material_preset_id=1, material_name="C24"):
        self.Core = Core
        self.TFN = TFN
        self.Loc = Loc
        self.material_id = material_preset_id
        self.material_name = material_name

    def map_model(self, model: StructuralModel):
        objects = []
        
        # 1. Materials
        mat_enum_desc = self.Core.Material.DESCRIPTOR.fields_by_name['material_type'].enum_type
        timber_type_id = mat_enum_desc.values_by_name['MATERIAL_TYPE_TIMBER'].number
        
        for mat_id, mat_name in model.materials.items():
            objects.append(self.Core.Material(
                no=mat_id, 
                name=mat_name,
                material_type=timber_type_id
            ))

        # 2. Nodes (Z-Inversion für RFEM)
        for n in model.nodes:
            # RFEM default Z points down
            objects.append(self.Core.Node(
                no=n.id, 
                coordinate_1=n.point.x, 
                coordinate_2=n.point.y, 
                coordinate_3=-n.point.z
            ))

        # 3. Sections
        for s in model.sections:
            objects.append(self.Core.CrossSection(
                no=s.id, 
                name=s.name, 
                material=s.material_id
            ))
        
        # 4. Members
        for m in model.members:
            if m.is_rigid:
                # TYPE_RIGID = 2
                objects.append(self.Core.Member(
                    no=m.id, 
                    type=2,
                    node_start=m.node_start, 
                    node_end=m.node_end
                ))
            else:
                objects.append(self.Core.Member(
                    no=m.id, 
                    node_start=m.node_start, 
                    node_end=m.node_end,
                    cross_section_start=m.section_id, 
                    cross_section_end=m.section_id,
                    is_rotated=bool(m.rotation != 0.0),
                    rotation_specification_type=0, 
                    rotation_angle=float(m.rotation)
                ))

        # 5. Supports
        for s in model.supports:
            objects.append(self.TFN.NodalSupport(
                no=s.id,
                nodes=s.nodes,
                name=s.name,
                spring_x=s.ux,
                spring_y=s.uy,
                spring_z=s.uz,
                rotational_restraint_x=s.rx,
                rotational_restraint_y=s.ry,
                rotational_restraint_z=s.rz
            ))

        # 6. Basic Load Case / Settings
        sas1 = self.Loc.StaticAnalysisSettings(no=1, name="Linear Analysis", analysis_type=0)
        lc1 = self.Loc.LoadCase(
            no=1, 
            name="Self-Weight", 
            action_category=11, 
            analysis_type=1,
            self_weight_active=True,
            self_weight_factor_z=1.0,
            static_analysis_settings=1
        )
        objects.append(sas1)
        objects.append(lc1)

        return objects
