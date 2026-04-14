from compas_timber_fea.core.model import StructuralNode

class NodeMapper:
    """Konvertiert neutrale Knoten in Dlubal PB Objekte"""
    def __init__(self, Core):
        self.Core = Core

    def map(self, node: StructuralNode):
        # RFEM default Z points down, so we negate COMPAS Z
        return self.Core.Node(
            no=node.id, 
            coordinate_1=node.point.x, 
            coordinate_2=node.point.y, 
            coordinate_3=-node.point.z
        )
