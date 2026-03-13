# SAF (Structural Analysis Format) Definition
# This file contains the schema definitions for SAF spreadsheets based on the 1.0.5+ standard.

# Column order and names for all sheets except Model and Project (which are vertical)
SHEETS = {
    'StructuralMaterial': [
        'Name', 'Type', 'Subtype', 'Quality', 'Unit mass [kg/m3]', 'E modulus [MPa]', 'G modulus [MPa]', 'Poisson Coefficient', 'Thermal expansion [1/K]', 'Design properties', 'Id'
    ],
    'StructuralCrossSection': [
        'Name', 'Material', 'Cross-section type', 'Shape', 'Parameters [mm]', 'Profile', 'Form code', 'Description ID of the profile', 'A [m2]', 'Iy [m4]', 'Iz [m4]', 'It [m4]', 'Iw [m6]', 'Wply [m3]', 'Wplz [m3]', 'Id'
    ],
    'StructuralPointConnection': [
        'Name', 'Coordinate X [m]', 'Coordinate Y [m]', 'Coordinate Z [m]', 'Id'
    ],
    'StructuralCurveMember': [
        'Name', 'Type', 'Cross section', 'Arbitrary definition', 'Nodes', 'Segments', 'Begin node', 'End node', 'Internal nodes', 'Length [m]', 'Geometrical shape', 'Parent ID', 'LCS', 'LCS Rotation [deg]', 'Coordinate X [m]', 'Coordinate Y [m]', 'Coordinate Z [m]', 'System line', 'Eccentricity ey [mm]', 'Eccentricity ez [mm]', 'Layer', 'Behaviour in analysis', 'Color', 'Id'
    ],
    'StructuralPointSupport': [
        'Name', 'Point connection', 'Support Condition X', 'Support Condition Y', 'Support Condition Z', 'Support Condition Rx', 'Support Condition Ry', 'Support Condition Rz'
    ],
    'StructuralLoadGroup': [
        'Name', 'Action category', 'Id'
    ],
    'StructuralLoadCase': [
        'Name', 'Description', 'Action category', 'Variable load type', 'Id'
    ],
}
