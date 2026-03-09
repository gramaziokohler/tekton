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
    x_D.unitize()
    
    # 2. Target Y-Vector in Dlubal Space
    y_target = Vector(orientation_vector.x, orientation_vector.y, -orientation_vector.z)
    
    # 3. Dlubal Default Orientation Logic
    global_z_dlubal = Vector(0, 0, 1)
    if abs(x_D[2]) > 0.999: # fast vertikal
        y_default = Vector(0, 1, 0)
    else:
        y_default = global_z_dlubal.cross(x_D)
        y_default.unitize()
        
    dot = max(-1.0, min(1.0, y_default.dot(y_target)))
    det = x_D.dot(y_default.cross(y_target))
    
    return math.atan2(det, dot)
