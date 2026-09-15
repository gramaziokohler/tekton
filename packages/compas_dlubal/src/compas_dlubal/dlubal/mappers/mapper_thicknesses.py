class ThicknessMapper:
    def __init__(self, Core):
        self.Core = Core

    def map(self, structural_thickness, material_id=None):
        """Maps StructuralThickness to Dlubal Thickness.

        ``material_id`` overrides the neutral material id - the importer
        passes the surface variant of the material (orthotropic 2D), because
        the library timber material a member uses cannot carry a plate.
        """
        return self.Core.Thickness(
            no=structural_thickness.id,
            name=structural_thickness.name,
            material=structural_thickness.material_id if material_id is None else material_id,
            uniform_thickness=structural_thickness.thickness
        )
