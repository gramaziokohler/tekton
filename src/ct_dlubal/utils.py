import math
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Vector

# NodeManager bleibt hier, da er agnostisch ist (Punkte deduplizieren)
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
