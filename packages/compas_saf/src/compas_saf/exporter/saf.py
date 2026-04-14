import os
import pandas as pd
from compas_timber_fea.exporter.base import BaseExporter
from compas_saf.exporter.saf_schema import SHEETS

class SAFExporter(BaseExporter):
    """Exporter für das Structural Analysis Format (SAF) mittels Excel (.xlsx)."""
    
    def export(self, filepath: str):
        print(f"Starte SAF-Export nach: {filepath}")
        
        # Determine model name from filename (standard SAF behavior)
        model_name = os.path.basename(filepath).split('.')[0]

        # 0. Model Info (CRITICAL: Needs exact labels and vertical layout)
        model_info = [
            {'Name': 'Name', 'test-model': model_name},
            {'Name': 'Description', 'test-model': ''},
            {'Name': 'Discipline', 'test-model': ''},
            {'Name': 'Level of detail', 'test-model': ''},
            {'Name': 'Status', 'test-model': ''},
            {'Name': 'Owner', 'test-model': ''},
            {'Name': 'Revision number', 'test-model': ''},
            {'Name': 'Created', 'test-model': ''},
            {'Name': 'Last update', 'test-model': ''},
            {'Name': 'Source type', 'test-model': ''},
            {'Name': 'Source application', 'test-model': 'Tekton SAF'},
            {'Name': 'Source company', 'test-model': ''},
            {'Name': 'Global coordinate system', 'test-model': 'Z vertical'},
            {'Name': 'LCS of cross-section', 'test-model': 'MinusZMinusYX'},
            {'Name': 'System of units', 'test-model': 'Metric'},
            {'Name': 'SAF Version', 'test-model': '1.0.5'},
            {'Name': 'Module version', 'test-model': ''},
            {'Name': 'Ignored objects', 'test-model': ''},
            {'Name': 'Ignored groups', 'test-model': ''},
            {'Name': 'Id', 'test-model': '{b248c262-72d9-42e0-8faa-674f17f0d9fb}'} # Dummy GUID
        ]
        df_model = pd.DataFrame(model_info).rename(columns={'test-model': model_name})

        # 1. Project Info (Vertical layout as well)
        project_info = [
            {'Name': 'Name', 'test-model': model_name},
            {'Name': 'Description', 'test-model': 'Exported from compas_timber'},
            {'Name': 'Project nr', 'test-model': '1'},
            {'Name': 'Created', 'test-model': ''},
            {'Name': 'Last update', 'test-model': ''},
            {'Name': 'Project type', 'test-model': ''},
            {'Name': 'Project kind', 'test-model': ''},
            {'Name': 'Building type', 'test-model': ''},
            {'Name': 'Status', 'test-model': ''},
            {'Name': 'Location', 'test-model': 'Zurich'}
        ]
        df_project = pd.DataFrame(project_info).rename(columns={'test-model': model_name})

        # 2. Materials Sheet
        materials_data = []
        for mat_id, mat_name in self.model.materials.items():
            data = {
                'Name': f"MAT{mat_id}",
                'Type': 'Timber',
                'Subtype': 'Timber',
                'Quality': mat_name,
                'Unit mass [kg/m3]': 420.0,
                'E modulus [MPa]': 11000.0,
                'G modulus [MPa]': 690.0,
                'Poisson Coefficient': 0.0,
                'Thermal expansion [1/K]': 0.0,
                'Design properties': '',
                'Id': f"MAT{mat_id}"
            }
            materials_data.append({col: data.get(col, '') for col in SHEETS['StructuralMaterial']})
        df_materials = pd.DataFrame(materials_data)

        # 3. Sections Sheet
        sections_data = []
        for i, sec in enumerate(self.model.sections):
            guid = f"sec-guid-{i}"
            mat_name = f"MAT{sec.material_id}"
            data = {
                'Name': sec.name,
                'Material': mat_name,
                'Cross-section type': 'Parametric',
                'Shape': 'Rectangle',
                'Parameters [mm]': f"{int(sec.width * 1000)};{int(sec.height * 1000)}",
                'Profile': 'R_M1',
                'Form code': '',
                'Description ID of the profile': '',
                'A [m2]': sec.width * sec.height,
                'Iy [m4]': (sec.width * (sec.height**3)) / 12.0,
                'Iz [m4]': (sec.height * (sec.width**3)) / 12.0,
                'It [m4]': 0.0,
                'Iw [m6]': 0.0,
                'Wply [m3]': 0.0,
                'Wplz [m3]': 0.0,
                'Id': guid
            }
            sections_data.append({col: data.get(col, '') for col in SHEETS['StructuralCrossSection']})
        df_sections = pd.DataFrame(sections_data)

        # 4. Nodes (Point Connections)
        nodes_data = []
        for node in self.model.nodes:
            data = {
                'Name': str(node.id),
                'Coordinate X [m]': round(float(node.point.x), 6),
                'Coordinate Y [m]': round(float(node.point.y), 6),
                'Coordinate Z [m]': round(-float(node.point.z), 6), # Invert Z
                'Id': f"node-guid-{node.id}"
            }
            nodes_data.append({col: data.get(col, '') for col in SHEETS['StructuralPointConnection']})
        df_nodes = pd.DataFrame(nodes_data)

        # 5. Members (Curve Members)
        members_data = []
        from compas_timber_fea.utils import calculate_beta_from_vector
        # Note: We need a beta calculation here that does not depend on Dlubal
        import math

        for i, mem in enumerate(self.model.members):
            section_name = "Unknown"
            for s in self.model.sections:
                if s.id == mem.section_id:
                    section_name = s.name
                    break
            
            # Rotation calculation
            p1 = None
            p2 = None
            for n in self.model.nodes:
                if n.id == mem.node_start: p1 = n.point
                if n.id == mem.node_end: p2 = n.point
            
            beta_deg = 0.0
            length = 0.0
            if p1 and p2:
                beta_rad = calculate_beta_from_vector(p1, p2, mem.orientation_vector)
                beta_deg = math.degrees(beta_rad)
                length = p1.distance_to_point(p2)

            data = {
                'Name': f"CM{mem.id}",
                'Type': 'Beam' if not mem.is_rigid else 'Rigid',
                'Cross section': section_name,
                'Arbitrary definition': '',
                'Nodes': f"{mem.node_start};{mem.node_end}",
                'Segments': 'Line',
                'Begin node': str(mem.node_start),
                'End node': str(mem.node_end),
                'Internal nodes': '',
                'Length [m]': round(length, 6),
                'Geometrical shape': 'Line',
                'Parent ID': '',
                'LCS': 'y by vector',
                'LCS Rotation [deg]': round(beta_deg, 4),
                'Coordinate X [m]': 0.0,
                'Coordinate Y [m]': 0.0,
                'Coordinate Z [m]': 0.0,
                'System line': 'Centre',
                'Eccentricity ey [mm]': '',
                'Eccentricity ez [mm]': '',
                'Layer': '',
                'Behaviour in analysis': 'Standard',
                'Color': '',
                'Id': f"mem-guid-{i}"
            }
            members_data.append({col: data.get(col, '') for col in SHEETS['StructuralCurveMember']})
        df_members = pd.DataFrame(members_data)

        # 6. Supports
        supports_data = []
        for supp in self.model.supports:
            is_inf = lambda x: x == float('inf') or x > 1e10
            for node_id in supp.nodes:
                stiff_x = "INF" if is_inf(supp.ux) else "0"
                stiff_y = "INF" if is_inf(supp.uy) else "0"
                stiff_z = "INF" if is_inf(supp.uz) else "0"
                stiff_rx = "INF" if is_inf(supp.rx) else "0"
                stiff_ry = "INF" if is_inf(supp.ry) else "0"
                stiff_rz = "INF" if is_inf(supp.rz) else "0"
                
                support_data = {
                    'Name': f"S_{supp.id}_{node_id}",
                    'Type': 'General',
                    'Node': str(node_id),
                    'ux': "Fixed" if is_inf(supp.ux) else "Free",
                    'uy': "Fixed" if is_inf(supp.uy) else "Free",
                    'uz': "Fixed" if is_inf(supp.uz) else "Free",
                    'fix': "Fixed" if is_inf(supp.rx) else "Free",
                    'fiy': "Fixed" if is_inf(supp.ry) else "Free",
                    'fiz': "Fixed" if is_inf(supp.rz) else "Free",
                    'Stiffness X [MN/m]': stiff_x,
                    'Stiffness Y [MN/m]': stiff_y,
                    'Stiffness Z [MN/m]': stiff_z,
                    'Stiffness Fix [MNm/rad]': stiff_rx,
                    'Stiffness Fiy [MNm/rad]': stiff_ry,
                    'Stiffness Fiz [MNm/rad]': stiff_rz,
                    'Id': f"S_{supp.id}_{node_id}"
                }
                # Ensure all columns match the schema
                full_support_data = {col: support_data.get(col, '') for col in SHEETS['StructuralPointSupport']}
                supports_data.append(full_support_data)
        df_supports = pd.DataFrame(supports_data)

        # 7. Loading (Groups and Cases)
        df_groups = pd.DataFrame([{col: {'Name': 'G', 'Load group type': 'Permanent', 'Relation': 'Standard', 'Load type': 'Permanent', 'Id': 'group-guid-1'}.get(col, '') for col in SHEETS['StructuralLoadGroup']}])

        lc_data = []
        for i, lc in enumerate(self.model.load_cases):
            data = {
                'Name': lc.name,
                'Description': f"Exported Case {lc.id}",
                'Action type': 'Permanent',
                'Load group': 'G',
                'Load type': 'Self-weight',
                'Duration': 'Long',
                'Id': f"lc-guid-{i}"
            }
            lc_data.append({col: data.get(col, '') for col in SHEETS['StructuralLoadCase']})
        df_lc = pd.DataFrame(lc_data)

        # Excel Export
        try:
            # FIX: pandas ExcelWriter needs a .xlsx extension for the engine to auto-detect correctly
            # or a specific engine like 'openpyxl'. We ensure we write to a temporary .xlsx 
            # if the target extension is .saf, then rename it.
            tmp_path = filepath
            if filepath.lower().endswith('.saf'):
                tmp_path = filepath + ".xlsx"

            with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
                # Write sheets without index
                df_model.to_excel(writer, sheet_name='Model', index=False)
                df_project.to_excel(writer, sheet_name='Project', index=False)
                df_materials.to_excel(writer, sheet_name='StructuralMaterial', index=False)
                df_sections.to_excel(writer, sheet_name='StructuralCrossSection', index=False)
                df_nodes.to_excel(writer, sheet_name='StructuralPointConnection', index=False)
                df_members.to_excel(writer, sheet_name='StructuralCurveMember', index=False)
                df_supports.to_excel(writer, sheet_name='StructuralPointSupport', index=False)
                df_groups.to_excel(writer, sheet_name='StructuralLoadGroup', index=False)
                df_lc.to_excel(writer, sheet_name='StructuralLoadCase', index=False)
            
            # If we used a temporary path, move it to the final .saf path
            if tmp_path != filepath:
                if os.path.exists(filepath):
                    os.remove(filepath)
                os.rename(tmp_path, filepath)

            print(f"SAF-Datei erfolgreich erstellt: {filepath}")
            return True
        except Exception as e:
            print(f"Fehler beim SAF-Export: {e}")
            return False

