import math
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Vector

# NodeManager (deprecated)
class NodeManager:
    # node manager to handle coordinates deduplication
    # rstab can only have one node at a given coordinate, plan is to round coordinates within tolerance

    def __init__(self, tolerance=1e-4):
        self.tolerance = tolerance
        self.points = {}
        self.nodes = []
        self._next_no = 1

    def get_node_number(self, point):
        # return existing node number or register a new one
        key = (round(point.x / self.tolerance), round(point.y / self.tolerance), round(point.z / self.tolerance))
        if key in self.points:
            return self.points[key]

        no = self._next_no
        self.points[key] = no
        self.nodes.append((no, point))
        self._next_no += 1
        return no
import math
from compas.geometry import Vector

def calculate_beta_from_vector(node_start_point, node_end_point, orientation_vector):
    """
    Berechnet den Dlubal Beta-Winkel aus einem agnostischen Orientierungs-Vektor.
    Speziell für RFEM/RSTAB da Z global nach unten geht.
    """
    # 1. Member Achse in Dlubal Space (Z invertiert zu COMPAS)
    x_D = Vector(
        node_end_point.x - node_start_point.x,
        node_end_point.y - node_start_point.y,
        -(node_end_point.z - node_start_point.z)
    )
    if x_D.length < 1e-9:
        return 0.0
    x_D.unitize()
    
    # 2. Target Y-Vector in Dlubal Space
    y_target = Vector(orientation_vector.x, orientation_vector.y, -orientation_vector.z)
    if y_target.length < 1e-9:
        return 0.0
    y_target.unitize()
    global_z_dlubal = Vector(0, 0, 1)
    if abs(x_D[2]) > 0.999: # fast vertikal
        y_default = Vector(0, 1, 0)
    else:
        # y_default = global_z_dlubal.cross(x_D)
        # Vector.cross returns a new Vector in COMPAS/generic logic
        try:
            y_default = global_z_dlubal.cross(x_D)
            if y_default.length < 1e-9:
                 y_default = Vector(0, 1, 0)
            else:
                 y_default.unitize()
        except ZeroDivisionError:
            y_default = Vector(0, 1, 0)
        
    dot = max(-1.0, min(1.0, y_default.dot(y_target)))
    det = x_D.dot(y_default.cross(y_target))
    
    return math.atan2(det, dot)

