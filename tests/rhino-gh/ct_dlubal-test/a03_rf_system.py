

from compas.datastructures import Mesh

from compas.geometry import Point 
from compas.geometry import Vector
from compas.geometry import Frame
from compas.geometry import intersection_line_line 

from compas_timber.elements import Beam
from compas_timber.model import TimberModel
from compas_timber.connections import TButtJoint
from compas_timber.connections import XLapJoint
from compas_timber.connections import LMiterJoint

from a03_mesh_relax import MeshRelax

class RFSystem:
    """RFSystem

    Class representing a reciprocal-framework (RF) structural system built on top
    of a ``compas.datastructures.Mesh``. The class manages per-edge
    centerlines and related metadata, offers utilities to relax and
    manipulate the underlying mesh and centerlines, and can convert the
    system into a timber model composed of beams and joints.

    Attributes
    ----------
    mesh : compas.datastructures.Mesh
        The underlying mesh. Many operations mutate this mesh in-place.
    target_boundary
        Optional boundary constraint passed to the mesh relaxer.
    target_corners
        Optional corners constraint passed to the mesh relaxer.
    target_surface
        Optional surface object (must provide ``closest_point``) used
        when snapping centerline endpoints to a surface.
    timber_model : compas_timber.model.TimberModel | None
        Cached timber model after calling ``compute_timber_model``.
    """




    def __init__(self, mesh, target_boundary=None, target_corners=None, target_surface=None):
        self.mesh = mesh
        self.target_boundary = target_boundary
        self.target_corners = target_corners
        self.target_surface = target_surface
        self.timber_model = None

    
    @property
    def centerlines(self) -> list:
        """List of centerlines for each edge in the mesh."""
        lines = [self.mesh.edge_attribute(edge, "centerline") for edge in self.mesh.edges()]
        return lines
    

    def copy(self) -> "RFSystem":
        """Create a copy of the RFSystem object."""
        return RFSystem(
            mesh=self.mesh.copy(),
            target_boundary=self.target_boundary,
            target_corners=self.target_corners,
            target_surface=self.target_surface,
        )


    # ---- RF SYSTEM DATASTRUCTURE ---- #
    def create_rf_datastructure(self) -> None:
        """
        For each edge on the mesh adds the attrivutes "next_edge" and "prev_edge" relative
        to the RF system. It also adds the "centerline" attribute to each edge.
        """
        for edge in self.mesh.edges():
            # set a centerline as atribute
            line = self.mesh.edge_line(edge)
            self.mesh.edge_attribute(edge, "centerline", line)
            # next and previos edges are not defined for boundary edges
            if self.mesh.is_edge_on_boundary(edge):
                continue
            # set next and previos edges attrivbutes
            next_edge = self._compute_next_rf_edge(edge)
            prev_edge = self._compute_prev_rf_edge(edge)
            self.mesh.edge_attribute(edge, "next_edge", next_edge)
            self.mesh.edge_attribute(edge, "prev_edge", prev_edge)
            # sets the edge normal attribute
            edge_normal = self._compute_edge_normal(edge)
            self.mesh.edge_attribute(edge, "normal", edge_normal)
        return None

    def _compute_next_rf_edge(self, edge):
        face = self.mesh.halfedge_face(edge)
        next_halffedge_index = (self.mesh.face_halfedges(face).index(edge) + 1) % len(self.mesh.face_halfedges(face))
        next_halfedge = self.mesh.face_halfedges(face)[next_halffedge_index]
        return next_halfedge


    def _compute_prev_rf_edge(self, edge):
        edge = (edge[1], edge[0])
        previous_halfedge = self._compute_next_rf_edge(edge)
        return previous_halfedge
    

    def _compute_edge_normal(self, edge) -> Vector:
        faces = self.mesh.edge_faces(edge)
        normal_1 = self.mesh.face_normal(faces[0])
        normal_2 = self.mesh.face_normal(faces[1])
        edge_normal = normal_1 + normal_2
        edge_normal.unitize()
        return edge_normal


    # ---- RF SYSTEM CENTERLINES ROTATION ---- #


    def eccentrize_centerlines(self, eccentricity: float) -> Mesh:
        """
        Moves the centerlines of the RF system edges according to the eccentricity value.
        A positive eccentricity moves the centerlines outwards, while a negative eccentricity
        """
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            next_edge = self.mesh.edge_attribute(edge, "next_edge")
            prev_edge = self.mesh.edge_attribute(edge, "prev_edge")
            centerline = self.mesh.edge_attribute(edge, "centerline")
            
            next_edge_direction = self.mesh.edge_direction(next_edge).unitized()
            prev_edge_direction = self.mesh.edge_direction(prev_edge).unitized()

            start_displacement = prev_edge_direction * eccentricity
            end_displacement = -start_displacement + next_edge_direction * eccentricity

            centerline.start += start_displacement
            centerline.end += end_displacement
            self.mesh.edge_attribute(edge, "centerline", centerline)
        return self.mesh     

    def eccentrize_centerlines_attractor_point(self, point: Point, factor: float) -> Mesh:
        """
        Moves the centerlines of the RF system edges towards or away from an attractor point.
        The amount of movement is determined by the distance to the point.
        """
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            next_edge = self.mesh.edge_attribute(edge, "next_edge")
            prev_edge = self.mesh.edge_attribute(edge, "prev_edge")
            centerline = self.mesh.edge_attribute(edge, "centerline")

            next_edge_direction = self.mesh.edge_direction(next_edge).unitized()
            prev_edge_direction = self.mesh.edge_direction(prev_edge).unitized()

            node_0 = self.mesh.vertex_point(edge[0])
            node_1 = self.mesh.vertex_point(edge[1])
            eccentricity_0 = point.distance_to_point(node_0) * factor
            eccentricity_1 = point.distance_to_point(node_1) * factor

            start_displacement = prev_edge_direction * eccentricity_0
            end_displacement = -start_displacement + next_edge_direction * eccentricity_1

            centerline.start += start_displacement
            centerline.end += end_displacement
            self.mesh.edge_attribute(edge, "centerline", centerline)
        return self.mesh



    def eccentrize_centerlines_attractor_curve(self, curve, factor: float) -> Mesh:
        """Eccentrize centerlines base on the distance to an attractor curve."""
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            next_edge = self.mesh.edge_attribute(edge, "next_edge")
            prev_edge = self.mesh.edge_attribute(edge, "prev_edge")
            centerline = self.mesh.edge_attribute(edge, "centerline")

            next_edge_direction = self.mesh.edge_direction(next_edge).unitized()
            prev_edge_direction = self.mesh.edge_direction(prev_edge).unitized()

            node_0 = self.mesh.vertex_point(edge[0])
            node_1 = self.mesh.vertex_point(edge[1])
            closest_point_0 = curve.closest_point(node_0)
            closest_point_1 = curve.closest_point(node_1)
            eccentricity_0 = closest_point_0.distance_to_point(node_0) * factor
            eccentricity_1 = closest_point_1.distance_to_point(node_1) * factor

            start_displacement = prev_edge_direction * eccentricity_0
            end_displacement = -start_displacement + next_edge_direction * eccentricity_1

            centerline.start += start_displacement
            centerline.end += end_displacement
            self.mesh.edge_attribute(edge, "centerline", centerline)
        return self.mesh
    

    def extend_centerlines(self, extension: float) -> Mesh:
        """
        Extends the centerlines of the RF system edges by a given extension value.
        """
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            extend_start = not self.mesh.is_vertex_on_boundary(edge[0])
            extend_end = not self.mesh.is_vertex_on_boundary(edge[1])
            print(extend_start, extend_end)
            centerline = self.mesh.edge_attribute(edge, "centerline")
            direction = centerline.direction.unitized()
            if extend_start and extend_end:
                centerline.start += direction * (-extension)
                centerline.end += direction * extension * 2
            elif extend_start and not extend_end:
                centerline.start += direction * (-extension)
                centerline.end += direction * extension
            elif not extend_start and extend_end:
                centerline.end += direction * extension

            centerline = self.mesh.edge_attribute(edge, "centerline", centerline)

    # ---- Mesh Relaxation ---- #

    def relax_mesh(self, iterations=50, damping=0.2, modifiers=None, snap_to_surface=True) -> Mesh:
        """Relax the mesh using the MeshRelax class."""
        relaxer = MeshRelax(
            mesh = self.mesh,
            iterations=iterations,
            damping=damping,
            boundary=self.target_boundary,
            corners=self.target_corners,
            surface=self.target_surface,
            snap_to_surface=snap_to_surface,
        )
        if modifiers:
            for mod in modifiers:
                relaxer.add_modifier(mod)
        self.mesh = relaxer.relax()
        return self.mesh

    def adjust_centerlines(self, iterations = 50, damping = 0.1):
        """
        Adjust the centerlines of the RF system edges by applying a spring system simulation.
        """

        for _ in range(iterations):

            self._compute_spring_forces(damping)
            self._apply_spring_forces()
    
    def snap_centerlines_to_surface(self):
        if not self.target_surface:
            return
        for edge in self.mesh.edges():
            centerline = self.mesh.edge_attribute(edge, "centerline")
            new_start = self.target_surface.closest_point(centerline.start)
            new_end = self.target_surface.closest_point(centerline.end)
            centerline.start = new_start
            centerline.end = new_end
            self.mesh.edge_attribute(edge, "centerline", centerline)


    # A02        

    def _compute_spring_forces(self, damping):
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            # get the data of the edge
            centerline = self.mesh.edge_attribute(edge, "centerline")
            next_edge = self.mesh.edge_attribute(edge, "next_edge")
            prev_edge = self.mesh.edge_attribute(edge, "prev_edge")
            next_centerline = self.mesh.edge_attribute(next_edge, "centerline")
            prev_centerline = self.mesh.edge_attribute(prev_edge, "centerline")

            # compute the vector to the end target
            _, target_end_point = intersection_line_line(centerline, next_centerline)
            vector_to_end_target = Vector.from_start_end(centerline.end, Point(*target_end_point)) * damping
            self.mesh.edge_attribute(edge, "vector_to_end_target", vector_to_end_target)

            # compute the vector to the start target
            _, target_start_point = intersection_line_line(centerline, prev_centerline)
            vector_to_start_target = Vector.from_start_end(centerline.start, Point(*target_start_point)) * damping
            self.mesh.edge_attribute(edge, "vector_to_start_target", vector_to_start_target)

    def _apply_spring_forces(self):
        for edge in self.mesh.edges():
            if self.mesh.is_edge_on_boundary(edge):
                continue
            centerline = self.mesh.edge_attribute(edge, "centerline")
            vector_to_end_target = self.mesh.edge_attribute(edge, "vector_to_end_target")
            vector_to_start_target = self.mesh.edge_attribute(edge, "vector_to_start_target")
            centerline.start += vector_to_start_target
            centerline.end += vector_to_end_target + vector_to_start_target.flipped()
            self.mesh.edge_attribute(edge, "centerline", centerline)

    
