import math
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Vector


def calculate_dlubal_rotation(frame_to_rotate):
    # calculate the dlubal rotation angle (beta) in radians
    x_axis = Vector(*frame_to_rotate.xaxis)
    z_axis = Vector(*frame_to_rotate.zaxis)
    global_z = Vector(0, 0, 1)

    # vertical member check
    if abs(x_axis.dot(global_z)) > 0.999:
        default_z = Vector(1, 0, 0)
    else:
        # dlubal's z-axis points downwards in a z-up system
        y_temp = global_z.cross(x_axis)
        y_temp.unitize()
        default_z = x_axis.cross(y_temp)
        default_z.unitize()

    dot = max(-1.0, min(1.0, default_z.dot(z_axis)))
    det = x_axis.dot(default_z.cross(z_axis))
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
