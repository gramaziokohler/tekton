from compas_timber_fea.core.model import StructuralSupport

class SupportMapper:
    """Konvertiert neutrale Auflager in Dlubal PB Objekte"""
    def __init__(self, TFN):
        self.TFN = TFN

    def map(self, support: StructuralSupport):
        return self.TFN.NodalSupport(
            no=support.id,
            nodes=support.nodes,
            name=support.name,
            spring_x=support.ux,
            spring_y=support.uy,
            spring_z=support.uz,
            rotational_restraint_x=support.rx,
            rotational_restraint_y=support.ry,
            rotational_restraint_z=support.rz
        )
