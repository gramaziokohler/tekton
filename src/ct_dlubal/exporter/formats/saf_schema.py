# SAF (Structural Analysis Format) Definition
# This file contains the schema definitions for SAF spreadsheets based on the 2.0.0 standard.

SHEETS = {
    'Project': [
        'Model Name', 'Project Name', 'Description', 'SAF Version', 'Unit System'
    ],
    'StructuralMaterial': [
        'Name', 'Material Type', 'Standard', 'E Modulus [N/mm2]', 'G Modulus [N/mm2]', 'Density [kg/m3]'
    ],
    'StructuralCrossSection': [
        'Name', 'Material', 'Shape Type', 'Form Code', 'Width [mm]', 'Height [mm]'
    ],
    'StructuralNode': [
        'Name', 'X [m]', 'Y [m]', 'Z [m]'
    ],
    'Structural1DMember': [
        'Name', 'Node Start', 'Node End', 'Cross Section', 'Rotation Angle [deg]', 'System Line Offset X [mm]', 'System Line Offset Y [mm]', 'System Line Offset Z [mm]'
    ],
    'StructuralSupportNode': [
        'Name', 'Node', 'Restraint X', 'Restraint Y', 'Restraint Z', 'Restraint Rx', 'Restraint Ry', 'Restraint Rz'
    ],
    'StructuralLoadCase': [
        'Name', 'Description', 'Action Category', 'Duration Class'
    ],
    'StructuralPointLoad': [
        'Name', 'Node', 'Load Case', 'Value FX [kN]', 'Value FY [kN]', 'Value FBZ [kN]', 'Value MX [kNm]', 'Value MY [kNm]', 'Value MZ [kNm]'
    ],
    'StructuralSurfaceMember': [
        'Name', 'Nodes', 'Thickness [mm]', 'Material'
    ]
}
