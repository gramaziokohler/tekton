class ThicknessMapper:
    def __init__(self, Core):
        self.Core = Core

    def map(self, structural_thickness):
        """Maps StructuralThickness to Dlubal Thickness."""
        return self.Core.Thickness(
            no=structural_thickness.id,
            name=structural_thickness.name,
            material_no=structural_thickness.material_id,
            uniform_thickness_thickness=structural_thickness.thickness
        )
