from compas.geometry import Point
from compas.geometry import Vector
from compas.geometry import Polyline
from compas.geometry import NurbsSurface
from compas.geometry import closest_point_on_polyline

from compas.datastructures import Mesh


class MeshRelax:
    """
    Relax a mesh by moving its vertices to their average position of their neighbors.

    Parameters
    ----------
    mesh : Mesh
        The mesh to relax.
    iterations : int, optional
        The number of iterations to perform.
    damping : float, optional
        The damping factor.
    boundary : Polyline, optional
        The boundary polyline.
    corners : list[Point], optional
        The corner points.
    surface : NurbsSurface, optional
        The surface to snap to.
    snap_to_surface : bool, optional
        Whether to snap to the surface.

    Attributes
    ----------
    mesh : Mesh
        The mesh to relax.
    iterations : int
        The number of iterations to perform.
    damping : float
        The damping factor.
    boundary : Polyline
        The boundary polyline.
    corners : list[Point]
        The corner points.
    surface : NurbsSurface
        The surface to snap to.
    snap_to_surface : bool
        Whether to snap to the surface.
    boundary_vertices : list[int]
        The boundary vertices.
    interior_vertices : list[int]
        The interior vertices.

    Methods
    -------
    relax()
        Relax the mesh.
    """

    def __init__(self, mesh: Mesh,
                 iterations = 50,
                 damping=0.2,
                 boundary: Polyline=None,
                 corners: list[Point]=None,
                 surface: NurbsSurface=None,
                 snap_to_surface: bool = True,):

        self.mesh = mesh
        self.iterations = iterations
        self.damping = damping
        self.boundary = boundary
        self.corners = corners
        self.surface = surface
        self.modifiers = []
        self.snap_to_surface = snap_to_surface

        self.assigned_vertices = set()

        self.set_vertices_default_attributes

    @property
    def boundary_vertices(self):
        """Return the boundary vertices of the mesh."""
        bvs = [v for v in self.mesh.vertices() if self.mesh.is_vertex_on_boundary(v)]
        return bvs

    @property
    def interior_vertices(self):
        """Return the interior vertices of the mesh."""
        ivs = [v for v in self.mesh.vertices() if not self.mesh.is_vertex_on_boundary(v)]
        return ivs


    # ---- MODIFIERS ---- #

    def set_vertices_default_attributes(self) -> None:
        """Set default attributes for all vertices."""
        for vertex in self.mesh.vertices():
            self.mesh.vertex_attribute(vertex, "fixed", False)
        return None



    def add_modifier(self, modifier) -> None:
        """Add a modifier to the mesh.

        Parameters:
            modifier (Callable): The modifier function to add.
        """
        self.modifiers.append(modifier)


    # ---- RELAXATION ---- #

    def relax(self) -> Mesh:
        """Relax the mesh using the specified parameters.

        Returns:
            Mesh: The relaxed mesh.
        """
        # Welcome to the spa tratment for your mesh!
        # if corners are not provided, we conside all boundary vertices as corners
        if not self.corners:
            self.corners = self.boundary.points[:-1]  # exclude last point because it's the same as the first one\

        print(self.mesh)
        self._apply_mesh_modifiers()

        for _ in range(self.iterations):

            self._compute_interior_forces()

            if self.boundary:
                self._compute_boundary_forces()
            if self.corners:
                self._compute_corner_forces()
            if self.modifiers:
                self._compute_force_modifiers()

            self._apply_forces()

        # Here is the mesh, relaxed and refreshed!~
        # Thank you for choosing our spa services.
        return self.mesh


    def _apply_mesh_modifiers(self) -> None:
        """Apply mesh modifiers to the mesh."""
        for mod in self.modifiers:
            if mod.type == "mesh_modifier":
                self.mesh = mod.apply(self, self.mesh)


    def _compute_boundary_forces(self) -> None:
        """Compute boundary forces for the mesh."""
        for vertex in self.boundary_vertices:

            if self.mesh.vertex_attribute(vertex, "not_boundary"):
                continue

            # vector towards closest point on polyline
            vertex_point = self.mesh.vertex_point(vertex)
            projected_point = Point(
                *closest_point_on_polyline(vertex_point, self.boundary)
            )
            force = Vector.from_start_end(vertex_point, projected_point)
            force *= self.damping
            self.mesh.vertex_attribute(vertex, "force", force)
        return None


    def _compute_interior_forces(self) -> None:
        """Compute interior forces for the mesh."""
        for vertex in self.mesh.vertices():
            if vertex in self.boundary_vertices:
                continue
            force = Vector(0, 0, 0)
            neighbors = self.mesh.vertex_neighbors(vertex)
            for neighbor in neighbors:
                neighbor_force = self.mesh.edge_vector((vertex, neighbor))
                force += neighbor_force * self.damping / len(neighbors)
            self.mesh.vertex_attribute(vertex, "force", force)
        return None


    def _compute_corner_forces(self) -> None:
        """Compute corner forces for the mesh."""
        self.assigned_vertices = set()
        for point in self.corners:
            # find the closes boundary vertex,
            # if the vertex has already been assigned, nevermind, just go on
            closest_vertex = min(self.boundary_vertices, key=lambda v: self.mesh.vertex_point(v).distance_to_point(point))
            # if distance  < 100:
            #     self.mesh.vertex_attribute(closest_vertex, "fixed", True)
            if closest_vertex in self.assigned_vertices:
                continue
            self.assigned_vertices.add(closest_vertex)
            # compute the force toward the corner
            vertex_point = self.mesh.vertex_point(closest_vertex)
            corner_force = Vector.from_start_end(vertex_point, point) * self.damping * 2
            # add the corner force to the existing force of the vertex
            force = self.mesh.vertex_attribute(closest_vertex, "force")
            force += corner_force
            self.mesh.vertex_attribute(closest_vertex, "force", force)
        return None


    def  _compute_force_modifiers(self) -> None:
        """Compute force modifiers for the mesh."""
        for mod in self.modifiers:
            if mod.type == "force_modifier":
                self.mesh = mod.apply(self, self.mesh)
        return None



    def _apply_forces(self) -> None:
        """Apply forces to the mesh."""
        for vertex in self.mesh.vertices():
             # get the force and compute the new point poistion of the vertex
            force = self.mesh.vertex_attribute(vertex, "force")
            vertex_point = self.mesh.vertex_point(vertex)
            new_point = vertex_point + force
            # project the new point onto the surface if required
            if self.surface and self.snap_to_surface:
                new_point = self.surface.closest_point(new_point)

            if self.mesh.vertex_attribute(vertex, "fixed"): # the vertex is fixed, do not move it
                continue

            # update the vertex position
            self.mesh.vertex_attribute(vertex, "x", new_point.x)
            self.mesh.vertex_attribute(vertex, "y", new_point.y)
            self.mesh.vertex_attribute(vertex, "z", new_point.z)
        return None
