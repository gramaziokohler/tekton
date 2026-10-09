import os
import pandas as pd
from compas_timber_fea.core.materials import Material
from compas_timber_fea.exporter.base import BaseExporter
from compas_saf.exporter.saf_schema import SHEETS


#: Neutral action categories -> SAF 'Action type' enum values.
SAF_ACTION_TYPES = {
    'PERMANENT': 'Permanent',
    'VARIABLE': 'Variable',
    'SNOW': 'Variable',
    'WIND': 'Variable',
    'ACCIDENTAL': 'Accidental',
}


def _saf_constraint(value, rigid_threshold=1e10):
    """Translate a neutral stiffness value into a SAF constraint and stiffness.

    inf (or a very large value) means fully restrained, 0 means free, and any
    finite value in between is a spring, which SAF expresses as 'Flexible' plus
    a numeric stiffness.
    """
    if value == float('inf') or value > rigid_threshold:
        return 'Rigid', ''
    if not value:
        return 'Free', ''
    return 'Flexible', value


class UnsupportedModel(Exception):
    """The model holds something a SAF export would silently change.

    Raised rather than returning False, because the caller's natural reaction
    to False is to look for a file that is not there - while the real problem
    is that writing one would have been wrong.
    """


class FidelityReport:
    """What a SAF export would drop, split by whether it changes the answer."""

    def __init__(self):
        #: Losses that make the exported model a *different structure*.
        self.refuses = []
        #: Losses that make it an *emptier* one - visible to whoever opens it.
        self.warnings = []

    def describe(self):
        lines = []
        if self.refuses:
            lines.append("This model cannot be written to SAF without changing it:")
            lines.extend("  - {}".format(reason) for reason in self.refuses)
            lines.append(
                "Use the RFEM or OpenSees backend instead, which carry these. "
                "To export the geometry anyway, knowing the rest is missing, "
                "pass allow_loss=True."
            )
        if self.warnings:
            lines.append("The SAF export does not carry:")
            lines.extend("  - {}".format(warning) for warning in self.warnings)
        return "\n".join(lines)


def fidelity_report(model):
    """What an export of `model` would lose.

    The split is by consequence, not by effort. A released member end that
    arrives rigid is a **wrong** answer in a file that looks right - nobody
    opening it has any way to notice. A missing load leaves an obviously empty
    load case, which the engineer sees immediately. So the first refuses and
    the second warns.
    """
    report = FidelityReport()

    released = [
        member.id for member in model.members
        if member.release_start is not None or member.release_end is not None
    ]
    if released:
        report.refuses.append(
            "{} member(s) carry a release ({}); SAF export writes no member hinges, "
            "so they would arrive rigid".format(
                len(released), ", ".join(str(i) for i in released[:5])
                + (" ..." if len(released) > 5 else ""))
        )

    surfaces = getattr(model, "surfaces", None) or []
    if surfaces:
        report.refuses.append(
            "{} surface(s); SAF export writes no surface sheet, so the plates "
            "would be missing entirely".format(len(surfaces))
        )

    line_supports = getattr(model, "line_supports", None) or []
    if line_supports:
        report.refuses.append(
            "{} line support(s); SAF export writes point supports only, so the "
            "model would arrive unsupported along those edges".format(len(line_supports))
        )

    loads = (
        len(getattr(model, "point_loads", None) or [])
        + len(getattr(model, "member_loads", None) or [])
        + len(getattr(model, "surface_loads", None) or [])
    )
    if loads:
        report.warnings.append(
            "{} load(s) - load cases are written, the loads in them are not".format(loads)
        )

    if getattr(model, "load_combinations", None):
        report.warnings.append(
            "{} load combination(s) - no combination sheet is written".format(
                len(model.load_combinations))
        )

    # Hardcoded in the cross-section sheet, so it applies to every export.
    report.warnings.append("torsional stiffness - 'It' is written as 0.0 for every section")

    return report


class SAFExporter(BaseExporter):
    """Exporter für das Structural Analysis Format (SAF) mittels Excel (.xlsx).

    The export is lossy, and deliberately noisy about it: see
    :func:`fidelity_report`. Losses that would change the structure raise
    :class:`UnsupportedModel` unless ``allow_loss`` is set.
    """

    def __init__(self, model, allow_loss=False):
        super().__init__(model)
        #: Write the file even when something structural would be lost.
        self.allow_loss = allow_loss
        #: Populated by :meth:`export`, so a caller can show the losses rather
        #: than relying on a console nobody is reading.
        self.report = None

    def export(self, filepath: str):
        self.report = fidelity_report(self.model)
        if self.report.refuses and not self.allow_loss:
            raise UnsupportedModel(self.report.describe())
        if self.report.refuses or self.report.warnings:
            print(self.report.describe())

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

        # 2. Materials Sheet - physical properties come from the neutral
        # material, not from a hardcoded grade. A GL24h model must not export
        # with C24 stiffness.
        materials_data = []
        for mat_id, mat_value in self.model.materials.items():
            material = Material.resolve(mat_value)
            data = {
                'Name': f"MAT{mat_id}",
                'Type': 'Timber',
                'Subtype': 'Timber',
                'Quality': material.name,
                'Unit mass [kg/m3]': material.density_mean,
                'E modulus [MPa]': material.E0_mean,
                'G modulus [MPa]': material.G_mean,
                'Poisson Coefficient': material.poisson,
                'Thermal expansion [1/K]': 0.0,
                'Design properties': material.standard,
                'Id': f"MAT{mat_id}"
            }
            materials_data.append({col: data.get(col, '') for col in SHEETS['StructuralMaterial']})
        df_materials = pd.DataFrame(materials_data, columns=SHEETS['StructuralMaterial'])

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
        df_sections = pd.DataFrame(sections_data, columns=SHEETS['StructuralCrossSection'])

        # 4. Nodes (Point Connections)
        nodes_data = []
        for node in self.model.nodes:
            data = {
                'Name': str(node.id),
                'Coordinate X [m]': round(float(node.point.x), 6),
                'Coordinate Y [m]': round(float(node.point.y), 6),
                'Coordinate Z [m]': round(float(node.point.z), 6),
                'Id': f"node-guid-{node.id}"
            }
            nodes_data.append({col: data.get(col, '') for col in SHEETS['StructuralPointConnection']})
        df_nodes = pd.DataFrame(nodes_data, columns=SHEETS['StructuralPointConnection'])

        # 5. Members (Curve Members)
        members_data = []
        sections_by_id = {s.id: s for s in self.model.sections}
        points_by_id = {n.id: n.point for n in self.model.nodes}

        for i, mem in enumerate(self.model.members):
            section = sections_by_id.get(mem.section_id)
            section_name = section.name if section else "Unknown"

            p1 = points_by_id.get(mem.node_start)
            p2 = points_by_id.get(mem.node_end)
            length = p1.distance_to_point(p2) if p1 and p2 else 0.0

            # SAF's "y by vector" takes the local y direction in global coordinates.
            # The neutral model already stores it, so no backend-specific rotation
            # convention is involved.
            orientation = mem.orientation_vector
            lcs_x, lcs_y, lcs_z = (float(orientation.x), float(orientation.y), float(orientation.z)) if orientation else (0.0, 0.0, 1.0)

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
                'Parent ID': mem.source_element_id or '',
                'LCS': 'y by vector',
                'LCS Rotation [deg]': 0.0,
                'Coordinate X [m]': round(lcs_x, 6),
                'Coordinate Y [m]': round(lcs_y, 6),
                'Coordinate Z [m]': round(lcs_z, 6),
                'System line': 'Centre',
                'Eccentricity ey [mm]': '',
                'Eccentricity ez [mm]': '',
                'Layer': '',
                'Behaviour in analysis': 'Standard',
                'Color': '',
                'Id': f"mem-guid-{i}"
            }
            members_data.append({col: data.get(col, '') for col in SHEETS['StructuralCurveMember']})
        df_members = pd.DataFrame(members_data, columns=SHEETS['StructuralCurveMember'])

        # 6. Supports
        supports_data = []
        for supp in self.model.supports:
            for node_id in supp.nodes:
                # SAF constraint enums: 'Rigid' (fully restrained), 'Free', or
                # 'Flexible' with a stiffness value. Stiffness columns apply to
                # flexible degrees of freedom only and stay empty otherwise.
                constraints = {}
                stiffnesses = {}
                for dof, value, stiffness_column in (
                    ('ux', supp.ux, 'Stiffness X [MN/m]'),
                    ('uy', supp.uy, 'Stiffness Y [MN/m]'),
                    ('uz', supp.uz, 'Stiffness Z [MN/m]'),
                    ('fix', supp.rx, 'Stiffness Fix [MNm/rad]'),
                    ('fiy', supp.ry, 'Stiffness Fiy [MNm/rad]'),
                    ('fiz', supp.rz, 'Stiffness Fiz [MNm/rad]'),
                ):
                    constraint, stiffness = _saf_constraint(value)
                    constraints[dof] = constraint
                    stiffnesses[stiffness_column] = stiffness

                support_data = {
                    'Name': f"S_{supp.id}_{node_id}",
                    'Type': 'Custom',
                    'Node': str(node_id),
                    **constraints,
                    **stiffnesses,
                    'Id': f"S_{supp.id}_{node_id}"
                }
                # Ensure all columns match the schema
                full_support_data = {col: support_data.get(col, '') for col in SHEETS['StructuralPointSupport']}
                supports_data.append(full_support_data)
        df_supports = pd.DataFrame(supports_data, columns=SHEETS['StructuralPointSupport'])

        # 7. Loading (Groups and Cases)
        df_groups = pd.DataFrame([{col: {'Name': 'G', 'Load group type': 'Permanent', 'Relation': 'Standard', 'Load type': 'Permanent', 'Id': 'group-guid-1'}.get(col, '') for col in SHEETS['StructuralLoadGroup']}])

        lc_data = []
        for i, lc in enumerate(self.model.load_cases):
            data = {
                'Name': lc.name,
                'Description': f"Exported Case {lc.id}",
                'Action type': SAF_ACTION_TYPES.get((lc.action_category or '').upper(), 'Variable'),
                'Load group': 'G',
                # SAF reserves the 'Self weight' load type for automatically
                # generated self-weight cases; everything else is 'Standard'.
                'Load type': 'Self weight' if lc.self_weight else 'Standard',
                'Duration': 'Long',
                'Id': f"lc-guid-{i}"
            }
            lc_data.append({col: data.get(col, '') for col in SHEETS['StructuralLoadCase']})
        df_lc = pd.DataFrame(lc_data, columns=SHEETS['StructuralLoadCase'])

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

