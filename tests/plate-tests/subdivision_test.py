# r: compas_timber>=1.0.0

from itertools import combinations

from compas.geometry import Point
from compas.geometry import Line
from compas.geometry import Polyline
from compas.geometry import Vector
from compas.geometry import Translation

from compas_timber.elements import Plate


class TimberPlateLineExtractor:
    def __init__(self, timber_model, reconnect=True, split=True, tolerance=1.0):
        self.timber_model = timber_model
        self.reconnect = reconnect
        self.split = split
        self.tolerance = tolerance

        self.plates = []
        self.outlines = []
        self.center_outlines = []
        self.split_piece_outlines = []
        self.center_edges = []
        self.internal_edges = []
        self.subdivision_edges = []
        self.all_edges = []
        self.nodes = []
        self.debug = []

    def extract(self):
        self._collect_plates()
        self._create_center_outlines()

        if self.reconnect:
            self._reconnect_joined_centerlines()

        if self.split:
            self._split_center_outlines_at_intersections()
            self._create_internal_edges_from_coplanar_foreign_edges()
            self._split_center_outlines_at_internal_edge_nodes()
            self._create_uv_subdivision_edges_from_internal_edges()
            self._create_split_piece_outlines()
            self.outlines = self.split_piece_outlines
        else:
            self.outlines = self.center_outlines

        self._create_edges_and_nodes()

        return (
            self.outlines,
            self.center_outlines,
            self.center_edges,
            self.internal_edges,
            self.subdivision_edges,
            self.all_edges,
            self.nodes,
            self.debug,
        )

    # --------------------------------------------------
    # collect
    # --------------------------------------------------

    def _collect_plates(self):
        self.plates = []

        for element in self.timber_model.elements():
            if isinstance(element, Plate):
                self.plates.append(element)

    # --------------------------------------------------
    # center outlines
    # --------------------------------------------------

    def _create_center_outlines(self):
        self.center_outlines = []

        for plate in self.plates:
            outline_a = plate.outline_a
            outline_b = plate.outline_b

            points_a = self._open_points(outline_a)
            points_b = self._open_points(outline_b)

            if len(points_a) != len(points_b):
                self.debug.append("Plate outlines have different point counts.")
                continue

            center_points = []

            for pa, pb in zip(points_a, points_b):
                center_points.append(
                    Point(
                        0.5 * (pa.x + pb.x),
                        0.5 * (pa.y + pb.y),
                        0.5 * (pa.z + pb.z),
                    )
                )

            center_points.append(center_points[0])
            self.center_outlines.append(Polyline(center_points))

    # --------------------------------------------------
    # reconnect centreline wall logic
    # --------------------------------------------------

    def _reconnect_joined_centerlines(self):
        for i, j in combinations(range(len(self.center_outlines)), 2):
            outline_a = self.center_outlines[i]
            outline_b = self.center_outlines[j]

            new_a = self._extend_outline_end_to_other_plane(outline_a, outline_b)
            new_b = self._extend_outline_end_to_other_plane(outline_b, outline_a)

            self.center_outlines[i] = new_a
            self.center_outlines[j] = new_b

    def _extend_outline_end_to_other_plane(self, moving_outline, target_outline):
        target_normal = self._polyline_normal(target_outline)
        target_point = self._open_points(target_outline)[0]

        points = self._open_points(moving_outline)
        direction = self._outline_long_direction(moving_outline)

        projections = [self._dot_point_vector(point, direction) for point in points]

        min_projection = min(projections)
        max_projection = max(projections)

        min_indices = [i for i, value in enumerate(projections) if abs(value - min_projection) <= self.tolerance]
        max_indices = [i for i, value in enumerate(projections) if abs(value - max_projection) <= self.tolerance]

        candidates = [min_indices, max_indices]

        best = None

        for indices in candidates:
            if not indices:
                continue

            side_midpoint = self._average_point([points[i] for i in indices])
            vector_to_plane = Vector.from_start_end(side_midpoint, target_point)
            signed_distance = vector_to_plane.dot(target_normal)
            distance = abs(signed_distance)

            if best is None or distance < best[0]:
                best = (distance, signed_distance, indices, target_normal)

        if best is None:
            return moving_outline

        distance, signed_distance, indices, target_normal = best
        max_reconnect_distance = self._estimate_plate_thickness_from_outline(moving_outline) * 1.1

        if distance > max_reconnect_distance:
            return moving_outline

        move_vector = target_normal * signed_distance

        new_points = []

        for index, point in enumerate(points):
            if index in indices:
                new_points.append(point.transformed(Translation.from_vector(move_vector)))
            else:
                new_points.append(point)

        new_points.append(new_points[0])
        return Polyline(new_points)

    # --------------------------------------------------
    # boundary splitting
    # --------------------------------------------------

    def _split_center_outlines_at_intersections(self):
        split_outlines = []

        for i, outline in enumerate(self.center_outlines):
            points = self._open_points(outline)
            edge_intersections = {edge_index: [] for edge_index in range(len(points))}

            for edge_index, p0 in enumerate(points):
                p1 = points[(edge_index + 1) % len(points)]
                edge_a = Line(p0, p1)

                for j, other_outline in enumerate(self.center_outlines):
                    if i == j:
                        continue

                    other_points = self._open_points(other_outline)

                    for q in other_points:
                        self._add_split_point_if_on_edge(q, p0, p1, edge_index, edge_intersections)

                    for other_edge_index, q0 in enumerate(other_points):
                        q1 = other_points[(other_edge_index + 1) % len(other_points)]
                        edge_b = Line(q0, q1)

                        intersection = self._line_line_intersection(edge_a, edge_b)

                        if intersection is None:
                            continue

                        if self._point_on_segment(intersection, p0, p1) and self._point_on_segment(intersection, q0, q1):
                            self._add_split_point_if_on_edge(intersection, p0, p1, edge_index, edge_intersections)

            split_outlines.append(self._rebuild_outline_with_splits(points, edge_intersections))

        self.center_outlines = split_outlines

    def _split_center_outlines_at_internal_edge_nodes(self):
        split_outlines = []

        internal_points = []

        for edge in self.internal_edges:
            internal_points.append(edge.start)
            internal_points.append(edge.end)

        for outline in self.center_outlines:
            points = self._open_points(outline)
            edge_intersections = {edge_index: [] for edge_index in range(len(points))}

            for edge_index, p0 in enumerate(points):
                p1 = points[(edge_index + 1) % len(points)]

                for q in internal_points:
                    self._add_split_point_if_on_edge(q, p0, p1, edge_index, edge_intersections)

            split_outlines.append(self._rebuild_outline_with_splits(points, edge_intersections))

        self.center_outlines = split_outlines

    def _add_split_point_if_on_edge(self, point, p0, p1, edge_index, edge_intersections):
        if not self._point_on_segment(point, p0, p1):
            return

        if self._points_equal(point, p0) or self._points_equal(point, p1):
            return

        t = self._segment_parameter(point, p0, p1)

        for existing_t, existing_point in edge_intersections[edge_index]:
            if abs(existing_t - t) <= 1e-9 or self._points_equal(existing_point, point):
                return

        edge_intersections[edge_index].append((t, point))

    def _rebuild_outline_with_splits(self, points, edge_intersections):
        new_points = []

        for edge_index, p0 in enumerate(points):
            new_points.append(p0)

            candidates = sorted(edge_intersections[edge_index], key=lambda item: item[0])

            for _, point in candidates:
                if not any(self._points_equal(point, existing) for existing in new_points):
                    new_points.append(point)

        new_points.append(new_points[0])
        return Polyline(new_points)

    # --------------------------------------------------
    # internal face edges
    # --------------------------------------------------

    def _create_internal_edges_from_coplanar_foreign_edges(self):
        self.internal_edges = []

        for i, target_outline in enumerate(self.center_outlines):
            target_points = self._open_points(target_outline)
            target_normal = self._polyline_normal(target_outline)
            target_plane_point = target_points[0]

            for j, other_outline in enumerate(self.center_outlines):
                if i == j:
                    continue

                other_points = self._open_points(other_outline)

                for k, q0 in enumerate(other_points):
                    q1 = other_points[(k + 1) % len(other_points)]

                    d0 = self._signed_distance_to_plane(q0, target_plane_point, target_normal)
                    d1 = self._signed_distance_to_plane(q1, target_plane_point, target_normal)

                    if abs(d0) <= self.tolerance and abs(d1) <= self.tolerance:
                        candidate = Line(q0, q1)

                        if self._line_has_relevant_part_inside_outline(candidate, target_outline, target_normal):
                            if not self._internal_edge_exists(candidate):
                                self.internal_edges.append(candidate)

    def _line_has_relevant_part_inside_outline(self, line, outline, normal):
        midpoint = self._average_point([line.start, line.end])

        if self._point_inside_or_on_outline_plane(midpoint, outline, normal):
            return True

        if self._point_inside_or_on_outline_plane(line.start, outline, normal):
            return True

        if self._point_inside_or_on_outline_plane(line.end, outline, normal):
            return True

        points = self._open_points(outline)

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]
            boundary = Line(p0, p1)
            intersection = self._line_line_intersection(line, boundary)

            if intersection is None:
                continue

            if self._point_on_segment(intersection, line.start, line.end) and self._point_on_segment(intersection, p0, p1):
                return True

        return False

    # --------------------------------------------------
    # UV subdivision graph
    # --------------------------------------------------

    def _create_uv_subdivision_edges_from_internal_edges(self):
        self.subdivision_edges = []

        for outline in self.center_outlines:
            normal = self._polyline_normal(outline)
            u_axis, v_axis, origin, normal = self._outline_uv_frame(outline)

            for internal_edge in self.internal_edges:
                if not self._line_lies_on_outline_plane(internal_edge, outline, normal):
                    continue

                if self._edge_matches_outline_boundary(internal_edge, outline):
                    continue

                for point in [internal_edge.start, internal_edge.end]:
                    if self._point_on_outline_boundary(point, outline):
                        continue

                    if not self._point_inside_or_on_outline_plane(point, outline, normal):
                        continue

                    subdivision_edges = self._uv_cross_subdivision_edges_from_point(
                        point,
                        outline,
                        origin,
                        u_axis,
                        v_axis,
                    )

                    for edge in subdivision_edges:
                        if not self._edge_matches_any(edge, self.subdivision_edges):
                            self.subdivision_edges.append(edge)

    def _uv_cross_subdivision_edges_from_point(self, point, outline, origin, u_axis, v_axis):
        points = self._open_points(outline)
        uv_points = [self._point_to_uv(p, origin, u_axis, v_axis) for p in points]

        u_values = [uv[0] for uv in uv_points]
        v_values = [uv[1] for uv in uv_points]

        u_min = min(u_values)
        u_max = max(u_values)
        v_min = min(v_values)
        v_max = max(v_values)

        u, v = self._point_to_uv(point, origin, u_axis, v_axis)

        p_bottom = self._uv_to_point(u, v_min, origin, u_axis, v_axis)
        p_top = self._uv_to_point(u, v_max, origin, u_axis, v_axis)
        p_left = self._uv_to_point(u_min, v, origin, u_axis, v_axis)
        p_right = self._uv_to_point(u_max, v, origin, u_axis, v_axis)

        candidates = [
            Line(p_bottom, point),
            Line(point, p_top),
            Line(p_left, point),
            Line(point, p_right),
        ]

        result = []

        for edge in candidates:
            if self._points_equal(edge.start, edge.end):
                continue

            if self._edge_matches_outline_boundary(edge, outline):
                continue

            result.append(edge)

        return result

    def _outline_uv_frame(self, outline):
        points = self._open_points(outline)
        origin = points[0]

        u_axis = self._outline_long_direction(outline)
        normal = self._polyline_normal(outline)

        v_axis = normal.cross(u_axis)

        if v_axis.length == 0:
            raise ValueError("Could not create UV frame.")

        v_axis.unitize()

        return u_axis, v_axis, origin, normal

    def _point_to_uv(self, point, origin, u_axis, v_axis):
        vector = Vector.from_start_end(origin, point)
        return vector.dot(u_axis), vector.dot(v_axis)

    def _uv_to_point(self, u, v, origin, u_axis, v_axis):
        vector = u_axis * u + v_axis * v
        return origin.transformed(Translation.from_vector(vector))

    # --------------------------------------------------
    # split-piece outlines
    # --------------------------------------------------

    def _create_split_piece_outlines(self):
        self.split_piece_outlines = []

        for outline in self.center_outlines:
            normal = self._polyline_normal(outline)
            u_axis, v_axis, origin, normal = self._outline_uv_frame(outline)

            outline_points = self._open_points(outline)
            uv_points = [self._point_to_uv(point, origin, u_axis, v_axis) for point in outline_points]

            u_values = [uv[0] for uv in uv_points]
            v_values = [uv[1] for uv in uv_points]

            u_min = min(u_values)
            u_max = max(u_values)
            v_min = min(v_values)
            v_max = max(v_values)

            split_u = [u_min, u_max]
            split_v = [v_min, v_max]

            for internal_edge in self.internal_edges:
                if not self._line_lies_on_outline_plane(internal_edge, outline, normal):
                    continue

                if self._edge_matches_outline_boundary(internal_edge, outline):
                    continue

                for point in [internal_edge.start, internal_edge.end]:
                    if self._point_on_outline_boundary(point, outline):
                        continue

                    if not self._point_inside_or_on_outline_plane(point, outline, normal):
                        continue

                    u, v = self._point_to_uv(point, origin, u_axis, v_axis)

                    if u_min + self.tolerance < u < u_max - self.tolerance:
                        self._add_unique_value(split_u, u)

                    if v_min + self.tolerance < v < v_max - self.tolerance:
                        self._add_unique_value(split_v, v)

            split_u = sorted(split_u)
            split_v = sorted(split_v)

            if len(split_u) == 2 and len(split_v) == 2:
                self.split_piece_outlines.append(outline)
                continue

            for i in range(len(split_u) - 1):
                for j in range(len(split_v) - 1):
                    u0 = split_u[i]
                    u1 = split_u[i + 1]
                    v0 = split_v[j]
                    v1 = split_v[j + 1]

                    if abs(u1 - u0) <= self.tolerance:
                        continue

                    if abs(v1 - v0) <= self.tolerance:
                        continue

                    p00 = self._uv_to_point(u0, v0, origin, u_axis, v_axis)
                    p10 = self._uv_to_point(u1, v0, origin, u_axis, v_axis)
                    p11 = self._uv_to_point(u1, v1, origin, u_axis, v_axis)
                    p01 = self._uv_to_point(u0, v1, origin, u_axis, v_axis)

                    midpoint = self._average_point([p00, p10, p11, p01])

                    if not self._point_inside_or_on_outline_plane(midpoint, outline, normal):
                        continue

                    self.split_piece_outlines.append(Polyline([p00, p10, p11, p01, p00]))

    def _add_unique_value(self, values, value):
        for existing in values:
            if abs(existing - value) <= self.tolerance:
                return

        values.append(value)

    # --------------------------------------------------
    # graph output
    # --------------------------------------------------

    def _create_edges_and_nodes(self):
        self.center_edges = []
        self.all_edges = []
        self.nodes = []

        for outline in self.outlines:
            points = self._open_points(outline)

            for i, p0 in enumerate(points):
                p1 = points[(i + 1) % len(points)]

                if not self._points_equal(p0, p1):
                    edge = Line(p0, p1)
                    self.center_edges.append(edge)
                    self.all_edges.append(edge)
                    self._add_node_unique(p0)
                    self._add_node_unique(p1)

        if self.split:
            for edge in self.internal_edges:
                self.all_edges.append(edge)
                self._add_node_unique(edge.start)
                self._add_node_unique(edge.end)

            for edge in self.subdivision_edges:
                self.all_edges.append(edge)
                self._add_node_unique(edge.start)
                self._add_node_unique(edge.end)

    def _add_node_unique(self, point):
        for existing in self.nodes:
            if self._points_equal(existing, point):
                return

        self.nodes.append(point)

    # --------------------------------------------------
    # helpers
    # --------------------------------------------------

    def _signed_distance_to_plane(self, point, plane_point, plane_normal):
        vector = Vector.from_start_end(plane_point, point)
        return vector.dot(plane_normal)

    def _line_lies_on_outline_plane(self, line, outline, normal):
        point_on_plane = self._open_points(outline)[0]

        d0 = self._signed_distance_to_plane(line.start, point_on_plane, normal)
        d1 = self._signed_distance_to_plane(line.end, point_on_plane, normal)

        return abs(d0) <= self.tolerance and abs(d1) <= self.tolerance

    def _point_inside_or_on_outline_plane(self, point, outline, normal):
        points = self._open_points(outline)

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]

            if self._point_on_segment(point, p0, p1):
                return True

        abs_normal = [abs(normal.x), abs(normal.y), abs(normal.z)]
        drop_axis = abs_normal.index(max(abs_normal))

        def project(p):
            if drop_axis == 0:
                return (p.y, p.z)
            elif drop_axis == 1:
                return (p.x, p.z)
            else:
                return (p.x, p.y)

        x, y = project(point)
        polygon = [project(p) for p in points]

        inside = False
        n = len(polygon)

        for i in range(n):
            x0, y0 = polygon[i]
            x1, y1 = polygon[(i + 1) % n]

            if (y0 > y) != (y1 > y):
                x_intersection = x0 + (y - y0) * (x1 - x0) / (y1 - y0)

                if x < x_intersection:
                    inside = not inside

        return inside

    def _point_on_outline_boundary(self, point, outline):
        points = self._open_points(outline)

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]

            if self._point_on_segment(point, p0, p1):
                return True

        return False

    def _edge_matches_outline_boundary(self, edge, outline):
        points = self._open_points(outline)

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]
            boundary = Line(p0, p1)

            if self._same_edge(edge, boundary):
                return True

        return False

    def _line_line_intersection(self, line_a, line_b):
        a0 = line_a.start
        a1 = line_a.end

        b0 = line_b.start
        b1 = line_b.end

        da = Vector.from_start_end(a0, a1)
        db = Vector.from_start_end(b0, b1)

        cross = da.cross(db)

        if cross.length <= self.tolerance:
            return None

        plane_normal = cross
        plane_normal.unitize()

        vector_between = Vector.from_start_end(a0, b0)

        if abs(vector_between.dot(plane_normal)) > self.tolerance:
            return None

        abs_normal = [abs(plane_normal.x), abs(plane_normal.y), abs(plane_normal.z)]
        drop_axis = abs_normal.index(max(abs_normal))

        def project(point):
            if drop_axis == 0:
                return (point.y, point.z)
            elif drop_axis == 1:
                return (point.x, point.z)
            else:
                return (point.x, point.y)

        ax0, ay0 = project(a0)
        ax1, ay1 = project(a1)

        bx0, by0 = project(b0)
        bx1, by1 = project(b1)

        denominator = (ax0 - ax1) * (by0 - by1) - (ay0 - ay1) * (bx0 - bx1)

        if abs(denominator) <= self.tolerance:
            return None

        determinant_a = ax0 * ay1 - ay0 * ax1
        determinant_b = bx0 * by1 - by0 * bx1

        x = (determinant_a * (bx0 - bx1) - (ax0 - ax1) * determinant_b) / denominator
        y = (determinant_a * (by0 - by1) - (ay0 - ay1) * determinant_b) / denominator

        if drop_axis == 0:
            return Point(a0.x, x, y)
        elif drop_axis == 1:
            return Point(x, a0.y, y)
        else:
            return Point(x, y, a0.z)

    def _open_points(self, polyline):
        points = list(polyline.points)

        if points[0] == points[-1]:
            points = points[:-1]

        return points

    def _polyline_normal(self, polyline):
        points = self._open_points(polyline)

        nx = ny = nz = 0.0

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]

            nx += (p0.y - p1.y) * (p0.z + p1.z)
            ny += (p0.z - p1.z) * (p0.x + p1.x)
            nz += (p0.x - p1.x) * (p0.y + p1.y)

        normal = Vector(nx, ny, nz)

        if normal.length == 0:
            raise ValueError("Could not calculate polyline normal.")

        normal.unitize()
        return normal

    def _outline_long_direction(self, polyline):
        points = self._open_points(polyline)

        longest = None
        longest_length = 0.0

        for i, p0 in enumerate(points):
            p1 = points[(i + 1) % len(points)]
            vector = Vector.from_start_end(p0, p1)

            if vector.length > longest_length:
                longest = vector
                longest_length = vector.length

        if longest is None or longest.length == 0:
            raise ValueError("Could not determine outline direction.")

        longest.unitize()
        return longest

    def _estimate_plate_thickness_from_outline(self, center_outline):
        return 250.0

    def _average_point(self, points):
        x = sum(point.x for point in points) / len(points)
        y = sum(point.y for point in points) / len(points)
        z = sum(point.z for point in points) / len(points)

        return Point(x, y, z)

    def _dot_point_vector(self, point, vector):
        return point.x * vector.x + point.y * vector.y + point.z * vector.z

    def _points_equal(self, a, b):
        return a.distance_to_point(b) <= self.tolerance

    def _point_on_segment(self, point, a, b):
        ab = Vector.from_start_end(a, b)
        ap = Vector.from_start_end(a, point)

        if ab.length == 0:
            return False

        cross = ab.cross(ap)

        if cross.length > self.tolerance:
            return False

        dot = ap.dot(ab)

        if dot < -self.tolerance:
            return False

        if dot > ab.dot(ab) + self.tolerance:
            return False

        return True

    def _segment_parameter(self, point, a, b):
        ab = Vector.from_start_end(a, b)
        ap = Vector.from_start_end(a, point)

        length_squared = ab.dot(ab)

        if length_squared == 0:
            return 0.0

        return ap.dot(ab) / length_squared

    def _edge_matches_any(self, edge, edges):
        for other in edges:
            if self._same_edge(edge, other):
                return True

        return False

    def _internal_edge_exists(self, edge):
        return self._edge_matches_any(edge, self.internal_edges)

    def _same_edge(self, a, b):
        return (
            self._points_equal(a.start, b.start)
            and self._points_equal(a.end, b.end)
        ) or (
            self._points_equal(a.start, b.end)
            and self._points_equal(a.end, b.start)
        )


# --------------------------------------------------
# Grasshopper usage
# --------------------------------------------------

extractor = TimberPlateLineExtractor(
    timber_model=timber_model,
    reconnect=True,
    split=split,
    tolerance=1.0,
)

outlines, center_outlines, center_edges, internal_edges, subdivision_edges, all_edges, nodes, debug = extractor.extract()

outline_count = len(outlines)
edge_count = len(center_edges)
internal_edge_count = len(internal_edges)
subdivision_edge_count = len(subdivision_edges)
all_edge_count = len(all_edges)
node_count = len(nodes)