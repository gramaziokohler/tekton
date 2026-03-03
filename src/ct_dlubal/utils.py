from __future__ import annotations

import math
from typing import Dict, List, Tuple

from compas.geometry import Frame, Point, Vector



def calculate_dlubal_rotation(frame_to_rotate: Frame) -> float:
    """
    Calculates the Dlubal rotation angle (beta) in radians from a COMPAS Frame.
    """
    x_axis = Vector(*frame_to_rotate.xaxis)
    z_axis = Vector(*frame_to_rotate.zaxis)
    global_z = Vector(0, 0, 1)

    # Vertical member check
    if abs(x_axis.dot(global_z)) > 0.999:
        default_z = Vector(1, 0, 0)
    else:
        # Dlubal default z points 'away' from global Z (downwards in Z-up)
        y_temp = global_z.cross(x_axis)
        y_temp.unitize()
        default_z = x_axis.cross(y_temp)
        default_z.unitize()

    dot = max(-1.0, min(1.0, default_z.dot(z_axis)))
    det = x_axis.dot(default_z.cross(z_axis))
    return math.atan2(det, dot)


class NodeManager:
    """
    Manages node deduplication.
    """

    def __init__(self, tolerance: float = 1e-4):
        """Initializes with a specific geometric tolerance."""
        self.tolerance = tolerance
        self.points: Dict[Tuple[int, int, int], int] = {}
        self.nodes: List[Tuple[int, Point]] = []
        self._next_no = 1

    def get_node_number(self, point: Point) -> int:
        """Returns existing node number or creates a new one for shared geometry."""
        key = (round(point.x / self.tolerance), round(point.y / self.tolerance), round(point.z / self.tolerance))
        if key in self.points:
            return self.points[key]

        no = self._next_no
        self.points[key] = no
        self.nodes.append((no, point))
        self._next_no += 1
        return no

