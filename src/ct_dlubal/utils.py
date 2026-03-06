import math
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Vector


def calculate_dlubal_rotation(frame_to_rotate):
    # calculate the dlubal rotation angle (beta) in radians
    # Dlubal imports nodes with Z negated (Z goes down), so we need 
    # to evaluate axes in Dlubal's coordinate space.
    x_D = Vector(frame_to_rotate.xaxis[0], frame_to_rotate.xaxis[1], -frame_to_rotate.xaxis[2])
    
    # Target axes in Dlubal space
    y_target = Vector(frame_to_rotate.yaxis[0], frame_to_rotate.yaxis[1], -frame_to_rotate.yaxis[2])
    
    # Dlubal's global Z goes downwards.
    global_z_dlubal = Vector(0, 0, 1)

    # Calculate Default Dlubal local axes for this member
    if abs(x_D[2]) > 0.999: # vertical
        y_default = Vector(0, 1, 0) if x_D[2] > 0 else Vector(0, 1, 0)
    else:
        # Default y is horizontal such that z points downwards
        y_default = global_z_dlubal.cross(x_D)
        y_default.unitize()
        
    z_default = x_D.cross(y_default)
    z_default.unitize()

    # The angle from y_default to y_target around x_D
    dot = max(-1.0, min(1.0, y_default.dot(y_target)))
    det = x_D.dot(y_default.cross(y_target))
    
    # Return the angle beta around x_D
    return math.atan2(det, dot)


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
