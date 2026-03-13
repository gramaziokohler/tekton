import pandas as pd
from ct_dlubal.exporter.base import BaseExporter
from ct_dlubal.exporter.formats.saf_schema import SHEETS

class SAFExporter(BaseExporter):
    """Exporter für das Structural Analysis Format (SAF) mittels Excel (.xlsx)."""
    
    def export(self, filepath: str):
        print(f"Starte SAF-Export nach: {filepath}")
        
        # 1. Project Info (Minimal SAF requirement)
        df_project = pd.DataFrame([{
            'Model Name': 'CT_Dlubal Export',
            'Project Name': 'Timber Project',
            'Description': 'Exported from compas_timber',
            'SAF Version': '2.0.0',
            'Unit System': 'Metric'
        }])

        # 2. Materials Sheet
        materials_data = []
        for mat_id, mat_name in self.model.materials.items():
            materials_data.append({
                'Name': mat_name,
                'Material Type': 'Timber',
                'Standard': 'Eurocode',
                'E Modulus [N/mm2]': 11000,
                'G Modulus [N/mm2]': 690,
                'Density [kg/m3]': 420
            })
        df_materials = pd.DataFrame(materials_data)

        # 3. Sections Sheet
        sections_data = []
        for sec in self.model.sections:
            mat_name = self.model.materials.get(sec.material_id, "Unknown")
            sections_data.append({
                'Name': sec.name,
                'Material': mat_name,
                'Shape Type': 'Rectangle',
                'Form Code': 'CU-R-H', # Custom Rectangular Hollow/Solid
                'Width [mm]': sec.width * 1000.0,
                'Height [mm]': sec.height * 1000.0
            })
        df_sections = pd.DataFrame(sections_data)

        # 4. Nodes Sheet
        nodes_data = []
        for node in self.model.nodes:
            nodes_data.append({
                'Name': str(node.id),
                'X [m]': float(node.point.x),
                'Y [m]': float(node.point.y),
                'Z [m]': float(node.point.z)
            })
        df_nodes = pd.DataFrame(nodes_data)

        # 5. Members Sheet (1D)
        members_data = []
        for mem in self.model.members:
            # Safely fetch section name
            section_name = "Unknown"
            for s in self.model.sections:
                if s.id == mem.section_id:
                    section_name = s.name
                    break

            members_data.append({
                'Name': str(mem.id),
                'Node Start': str(mem.node_start),
                'Node End': str(mem.node_end),
                'Cross Section': section_name,
                'Rotation Angle [deg]': 0.0, # TODO: orientation to angle
                'System Line Offset X [mm]': 0.0,
                'System Line Offset Y [mm]': 0.0,
                'System Line Offset Z [mm]': 0.0
            })
        df_members = pd.DataFrame(members_data)

        # 6. Supports Sheet
        supports_data = []
        for supp in self.model.supports:
            # Check for infinites to map to "Fixed"
            is_inf = lambda x: x == float('inf') or x > 1e10
            for node_id in supp.nodes:
                supports_data.append({
                    'Name': f"S_{supp.id}_{node_id}",
                    'Node': str(node_id),
                    'Restraint X': 'Fixed' if is_inf(supp.ux) else 'Free',
                    'Restraint Y': 'Fixed' if is_inf(supp.uy) else 'Free',
                    'Restraint Z': 'Fixed' if is_inf(supp.uz) else 'Free',
                    'Restraint Rx': 'Fixed' if is_inf(supp.rx) else 'Free',
                    'Restraint Ry': 'Fixed' if is_inf(supp.ry) else 'Free',
                    'Restraint Rz': 'Fixed' if is_inf(supp.rz) else 'Free'
                })
        df_supports = pd.DataFrame(supports_data)

        # Excel Export mit mehreren Sheets und SAF-Schema Spalten
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Reorder columns to stay standard-compliant where possible
                df_project.reindex(columns=SHEETS['Project']).to_excel(writer, sheet_name='Project', index=False)
                df_materials.reindex(columns=SHEETS['StructuralMaterial']).to_excel(writer, sheet_name='StructuralMaterial', index=False)
                df_sections.reindex(columns=SHEETS['StructuralCrossSection']).to_excel(writer, sheet_name='StructuralCrossSection', index=False)
                df_nodes.reindex(columns=SHEETS['StructuralNode']).to_excel(writer, sheet_name='StructuralNode', index=False)
                df_members.reindex(columns=SHEETS['Structural1DMember']).to_excel(writer, sheet_name='Structural1DMember', index=False)
                df_supports.reindex(columns=SHEETS['StructuralSupportNode']).to_excel(writer, sheet_name='StructuralSupportNode', index=False)
                
                # 7. Loading Sheets (Minimal)
                lc_data = []
                for lc in self.model.load_cases:
                    lc_data.append({
                        'Name': lc.name,
                        'Description': f"Exported Case {lc.id}",
                        'Action Category': lc.action_category,
                        'Duration Class': 'Permanent'
                    })
                if lc_data:
                    df_lc = pd.DataFrame(lc_data)
                    df_lc.reindex(columns=SHEETS['StructuralLoadCase']).to_excel(writer, sheet_name='StructuralLoadCase', index=False)

                pl_data = []
                for pl in self.model.point_loads:
                    # Find LC name
                    lc_name = "Self-Weight"
                    for lc in self.model.load_cases:
                        if lc.id == pl.load_case_id:
                            lc_name = lc.name
                            break
                    pl_data.append({
                        'Name': f"PL_{pl.id}",
                        'Node': str(pl.node_id),
                        'Load Case': lc_name,
                        'Value FX [kN]': float(pl.force.x),
                        'Value FY [kN]': float(pl.force.y),
                        'Value FBZ [kN]': float(pl.force.z),
                        'Value MX [kNm]': float(pl.moment.x),
                        'Value MY [kNm]': float(pl.moment.y),
                        'Value MZ [kNm]': float(pl.moment.z)
                    })
                if pl_data:
                    df_pl = pd.DataFrame(pl_data)
                    df_pl.reindex(columns=SHEETS['StructuralPointLoad']).to_excel(writer, sheet_name='StructuralPointLoad', index=False)

            print(f"SAF-Datei erfolgreich erstellt: {filepath}")
            return True
        except Exception as e:
            print(f"Fehler beim SAF-Export: {e}")
            return False

