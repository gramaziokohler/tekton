
import Rhino.Geometry as rg  #type: ignore

from compas_rhino.conversions import polyline_to_compas

from compas.geometry import Point
from compas.geometry import Polyline
from compas.geometry import NurbsSurface

from compas.datastructures import Mesh

class QuadMesher:
    """
    A class for generating a quad mesh from a single face Brep.

    Parameters:
        u_count (int): The number of divisions in the u direction.
        v_count (int): The number of divisions in the v direction.
        brep (rg.Brep): The Brep object.
        full_quads (bool): Whether to generate full quads or not.

    Attributes:
        mesh (Mesh): The generated mesh.
        points (list[Point]): The generated points.
    """

    def __init__(self, u_count: int, v_count: int, brep: rg.Brep, full_quads: bool = False):
        self.u_count = u_count
        self.v_count = v_count
        self.brep = brep
        self.full_quads = full_quads
        self.mesh = Mesh()
        self.points = []


    @property
    def face(self) -> rg.BrepFace:
        """
        The face of the Brep object.
        """
        return self.brep.Faces[0]

    @property
    def surface(self) -> rg.NurbsSurface:
        """
        The surface of the Brep object.
        """
        return NurbsSurface.from_native(self.face.UnderlyingSurface())

    @property
    def contour(self) -> Polyline:
        """
        The contour of the Brep object.
        """
        brep_loop = self.face.OuterLoop
        curve = brep_loop.To3dCurve()
        curve = curve.ToPolyline(1, 1, 0, 0)
        curve = curve.TryGetPolyline()[1]
        return polyline_to_compas(curve)

    @property
    def vertices(self) -> list[Point]:
        """
        The vertices of the Brep object.
        """
        vertices = [v.Location for v in self.brep.Vertices]
        return [rg.Point3d(v.X, v.Y, v.Z) for v in vertices]


    def is_point_on_face(self, point) -> bool:
        """
        Check if a point is on the face of the Brep object.
        """
        success, face_u, face_v = self.face.ClosestPoint(
            rg.Point3d(point.x, point.y, point.z)
        )
        relation = self.face.IsPointOnFace(face_u, face_v)
        if relation == rg.PointFaceRelation.Interior:
            return True
        if relation == rg.PointFaceRelation.Boundary:
            return True
        return False


    def _generate_vertices(self) -> None:
        """
        Generate vertices for the mesh.
        """
        range_domain_u = abs(self.surface.domain_u[1] - self.surface.domain_u[0])
        range_domain_v = abs(self.surface.domain_v[1] - self.surface.domain_v[0])

        for ui in range(self.u_count+1):
            for vi in range(self.v_count + 1):
                u = range_domain_u * ui/self.u_count + self.surface.domain_u[0]
                v = range_domain_v * vi/self.v_count + self.surface.domain_v[0]
                point = self.surface.point_at(u, v)
                self.mesh.add_vertex(x=point.x, y=point.y, z=point.z, u=ui, v=vi)
        return None

    def generate_mesh(self) -> None:
        """Generate the mesh.

        This method generates the mesh by calling the `_generate_vertices` method
        and then adding the faces of the mesh using the `add_face` method.

        Returns:
            None
        """
        self._generate_vertices()
        for u in range(self.u_count):
            for v in range(self.v_count):
                v1 = list(self.mesh.vertices_where({"u": u, "v": v}))[0]
                v2 = list(self.mesh.vertices_where({"u": u, "v": v+1}))[0]
                v3 = list(self.mesh.vertices_where({"u": u+1, "v": v+1}))[0]
                v4 = list(self.mesh.vertices_where({"u": u+1, "v": v}))[0]


                if self.full_quads and all([self.is_point_on_face(self.mesh.vertex_point(v)) for v in [v1, v2, v3, v4]]):
                    self.mesh.add_face([v1, v2, v3, v4])

                elif not self.full_quads:
                    face_vertices = []
                    if self.is_point_on_face(self.mesh.vertex_point(v1)):
                        face_vertices.append(v1)
                    if self.is_point_on_face(self.mesh.vertex_point(v2)):
                        face_vertices.append(v2)
                    if self.is_point_on_face(self.mesh.vertex_point(v3)):
                        face_vertices.append(v3)
                    if self.is_point_on_face(self.mesh.vertex_point(v4)):
                        face_vertices.append(v4)

                    if len(face_vertices) < 3:
                        continue
                    self.mesh.add_face(face_vertices)

        self.mesh.remove_unused_vertices()
        return self.mesh
class TriMesher:
    """
    A class for generating a triangular mesh from a Brep surface.

    Parameters
    ----------
    u_count : int
        The number of divisions in the u direction.
    v_count : int
        The number of divisions in the v direction.
    brep : rg.Brep
        The Brep surface to mesh.

    Attributes
    ----------
    mesh : Mesh
        The generated triangular mesh.
    points : list[Point]
        The points of the mesh.

    """

    def __init__(self, u_count: int, v_count: int, brep: rg.Brep):
        self.u_count = u_count
        self.v_count = v_count
        self.brep = brep
        self.mesh = Mesh()
        self.points = []


    @property
    def face(self) -> rg.BrepFace:
        """The Brep face to mesh."""
        return self.brep.Faces[0]

    @property
    def surface(self) -> rg.NurbsSurface:
        """The Nurbs surface to mesh."""
        return NurbsSurface.from_native(self.face.UnderlyingSurface())

    @property
    def contour(self) -> Polyline:
        """The contour of the Brep face."""
        brep_loop = self.face.OuterLoop
        curve = brep_loop.To3dCurve()
        curve = curve.ToPolyline(1, 1, 0, 0)
        curve = curve.TryGetPolyline()[1]
        return polyline_to_compas(curve)

    @property
    def vertices(self) -> list[Point]:
        """The vertices of the Brep face."""
        vertices = [v.Location for v in self.brep.Vertices]
        return [rg.Point3d(v.X, v.Y, v.Z) for v in vertices]

    def is_point_on_face(self, point) -> bool:
        """Check if a point is on the Brep face."""
        success, face_u, face_v = self.face.ClosestPoint(
            rg.Point3d(point.x, point.y, point.z)
        )
        relation = self.face.IsPointOnFace(face_u, face_v)
        if relation == rg.PointFaceRelation.Interior:
            return True
        if relation == rg.PointFaceRelation.Boundary:
            return True
        return False

    def _generate_vertices(self) -> None:
        """Generate vertices for the mesh."""
        u_line_count = self.u_count + 1
        v_line_count = self.v_count + 2

        range_domain_u = abs(self.surface.domain_u[1] -  self.surface.domain_u[0])
        range_domain_v = abs(self.surface.domain_v[1] -  self.surface.domain_v[0])

        for ui in range(u_line_count):
            for vi in range(v_line_count):
                u = range_domain_u * ui/(u_line_count-1) + self.surface.domain_u[0]
                v = range_domain_v * vi/(v_line_count-1) + self.surface.domain_v[0]
                point = self.surface.point_at(u, v)
                self.mesh.add_vertex(x=point.x, y=point.y, z=point.z, u=ui, v=vi)
        return None

    def generate_mesh(self) -> Mesh:
        """Generate a mesh from the Brep face."""
        self._generate_vertices()
        for ui in range(self.u_count):
            for vi in range(self.v_count):
                if (ui + vi) % 2 == 0:      # is even
                    v1 = list(self.mesh.vertices_where({"u": ui, "v": vi + 1}))[0]
                    v2 = list(self.mesh.vertices_where({"u": ui + 1, "v": vi + 2}))[0]
                    v3 = list(self.mesh.vertices_where({"u": ui + 1, "v": vi}))[0]
                else:
                    v1 = list(self.mesh.vertices_where({"u": ui, "v": vi}))[0]
                    v2 = list(self.mesh.vertices_where({"u": ui, "v": vi + 2}))[0]
                    v3 = list(self.mesh.vertices_where({"u": ui + 1, "v": vi + 1}))[0]

                face_vertices = []
                if self.is_point_on_face(self.mesh.vertex_point(v1)):
                    face_vertices.append(v1)
                if self.is_point_on_face(self.mesh.vertex_point(v2)):
                    face_vertices.append(v2)
                if self.is_point_on_face(self.mesh.vertex_point(v3)):
                    face_vertices.append(v3)

                if len(face_vertices) < 3:
                    continue

                self.mesh.add_face(face_vertices)
        self.mesh.remove_unused_vertices()
        return self.mesh
class HexaMesher:
    """
    HexaMesher is a class for generating hexahedral meshes from a given single face Brep.

    Parameters:
    -----------
    u_count : int
        The number of divisions in the u-direction.
    v_count : int
        The number of divisions in the v-direction.
    brep : rg.Brep
        The Brep object to be meshed.
    full_hexas : bool, optional
        If True, generate full hexahedra. If False, generate hexahedra with triangular faces.


    Attributes:
    -----------
    mesh : Mesh
        The generated hexahedral mesh.
    points : list[Point]
        The points of the mesh.

    """
    def __init__(self, u_count: int, v_count: int, brep: rg.Brep, full_hexas: bool = False):
        self.u_count = u_count
        self.v_count = v_count
        self.brep = brep
        self.full_hexas = full_hexas
        self.mesh = Mesh()
        self.points = []


    @property
    def face(self) -> rg.BrepFace:
        """The BrepFace object to be meshed."""
        return self.brep.Faces[0]

    @property
    def surface(self) -> rg.NurbsSurface:
        """The NurbsSurface object representing the face."""
        return NurbsSurface.from_native(self.face.UnderlyingSurface())

    @property
    def contour(self) -> Polyline:
        """The contour of the face as a Polyline."""
        brep_loop = self.face.OuterLoop
        curve = brep_loop.To3dCurve()
        curve = curve.ToPolyline(1, 1, 0, 0)
        curve = curve.TryGetPolyline()[1]
        return polyline_to_compas(curve)

    @property
    def vertices(self) -> list[Point]:
        """The vertices of the face as a list of Point objects."""
        vertices = [v.Location for v in self.brep.Vertices]
        return [rg.Point3d(v.X, v.Y, v.Z) for v in vertices]


    def is_point_on_face(self, point) -> bool:
        """Check if a point is on the face.

        Parameters:
            point (Point): The point to check.

        Returns:
            bool: True if the point is on the face, False otherwise.
        """
        _, face_u, face_v = self.face.ClosestPoint(
            rg.Point3d(point.x, point.y, point.z)
        )
        relation = self.face.IsPointOnFace(face_u, face_v)
        if relation == rg.PointFaceRelation.Interior:
            return True
        if relation == rg.PointFaceRelation.Boundary:
            return True
        return False


    def _generate_vertices(self) -> None:
        """Generate the vertices of the mesh.

        This method generates the vertices of the mesh by evaluating the surface at
        evenly spaced points in the parameter space. The vertices are added to the
        mesh object using the `add_vertex` method.

        Returns:
            None
        """
        u_lines = self.u_count * 2 + 2
        v_lines = self.v_count * 2 + 2

        range_domain_u = abs(self.surface.domain_u[1] - self.surface.domain_u[0])
        range_domain_v = abs(self.surface.domain_v[1] - self.surface.domain_v[0])

        for ui in range(u_lines+1):
            for vi in range(v_lines+1):
                u = range_domain_u * ui/(u_lines-1) + self.surface.domain_u[0]
                v = range_domain_v * vi/(v_lines-1) + self.surface.domain_v[0]
                point = self.surface.point_at(u, v)
                self.mesh.add_vertex(x=point.x, y=point.y, z=point.z, u=ui, v=vi)
        return None


    def generate_mesh(self) -> None:
        """Generate the mesh.

        This method generates the mesh by calling the `_generate_vertices` method
        and then adding the faces of the mesh using the `add_face` method.

        Returns:
            None
        """
        self._generate_vertices()
        for ui in range(self.u_count):
            for vi in range(self.v_count):
                if vi % 2 == 0:     # is even
                    v1 = list(self.mesh.vertices_where({"u": ui*2, "v": vi*2 + 1}))[0]
                    v2 = list(self.mesh.vertices_where({"u": ui*2, "v": vi*2 + 2}))[0]
                    v3 = list(self.mesh.vertices_where({"u": ui*2 + 1, "v": vi*2 + 3}))[0]
                    v4 = list(self.mesh.vertices_where({"u": ui*2 + 2, "v": vi*2 + 2}))[0]
                    v5 = list(self.mesh.vertices_where({"u": ui*2 + 2, "v": vi*2 + 1}))[0]
                    v6 = list(self.mesh.vertices_where({"u": ui*2 + 1, "v": vi*2 + 0}))[0]
                else:       # is odd
                    v1 = list(self.mesh.vertices_where({"u": ui*2 + 1, "v": vi*2 + 1}))[0]
                    v2 = list(self.mesh.vertices_where({"u": ui*2 + 1, "v": vi*2 + 2}))[0]
                    v3 = list(self.mesh.vertices_where({"u": ui*2 + 2, "v": vi*2 + 3}))[0]
                    v4 = list(self.mesh.vertices_where({"u": ui*2 + 3, "v": vi*2 + 2}))[0]
                    v5 = list(self.mesh.vertices_where({"u": ui*2 + 3, "v": vi*2 + 1}))[0]
                    v6 = list(self.mesh.vertices_where({"u": ui*2 + 2, "v": vi*2 + 0}))[0]

                if self.full_hexas and all([self.is_point_on_face(self.mesh.vertex_point(v)) for v in [v1, v2, v3, v4, v5, v6]]):
                    self.mesh.add_face([v1, v2, v3, v4, v5, v6])

                elif not self.full_hexas:
                    face_vertices = []
                    if self.is_point_on_face(self.mesh.vertex_point(v1)):
                        face_vertices.append(v1)
                    if self.is_point_on_face(self.mesh.vertex_point(v2)):
                        face_vertices.append(v2)
                    if self.is_point_on_face(self.mesh.vertex_point(v3)):
                        face_vertices.append(v3)
                    if self.is_point_on_face(self.mesh.vertex_point(v4)):
                        face_vertices.append(v4)
                    if self.is_point_on_face(self.mesh.vertex_point(v5)):
                        face_vertices.append(v5)
                    if self.is_point_on_face(self.mesh.vertex_point(v6)):
                        face_vertices.append(v6)

                    if len(face_vertices) < 3:
                        continue

                    self.mesh.add_face(face_vertices)

        self.mesh.remove_unused_vertices()
        return self.mesh
