from compas_timber_fea.core.model import StructuralNode

from compas_dlubal.dlubal.conventions import point_to_dlubal


class NodeMapper:
    """Konvertiert neutrale Knoten in Dlubal PB Objekte"""
    def __init__(self, Core):
        self.Core = Core

    def map(self, node: StructuralNode):
        # Neutral model is Z-up, Dlubal is Z-down; the conversion is a proper
        # rotation (see conventions.py) so chirality is preserved.
        x, y, z = point_to_dlubal(node.point)
        return self.Core.Node(
            no=node.id,
            coordinate_1=x,
            coordinate_2=y,
            coordinate_3=z
        )
