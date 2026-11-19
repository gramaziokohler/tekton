"""Member sets and load transfer surfaces: what an engineer's RFEM model has on top of members.

Both mirror the "Tragwerkskonzept 1 - Ingrid" model (2026-11-17): girders split at
every node but designed whole (member sets, Stabsaetze), and the roof's pressure
handed to the girders by a load transfer surface (Lastuebertragungsflaeche) rather
than as hand-distributed member loads.
"""

import math

from compas_timber_fea.core.load_distribution import edge_widths


class MemberSetMapper:
    def __init__(self, Core, numbering):
        self.Core = Core
        self.numbering = numbering

    def map(self, member_set):
        set_types = self.Core.MemberSet.DESCRIPTOR.fields_by_name["set_type"].enum_type
        kind = "SET_TYPE_CONTINUOUS" if member_set.set_type == "continuous" else "SET_TYPE_GROUP"
        return self.Core.MemberSet(
            no=self.numbering.member_set(member_set.id),
            user_defined_name_enabled=True,
            name=str(member_set.name)[:60],
            set_type=set_types.values_by_name[kind].number,
            members=[self.numbering.member(i) for i in member_set.member_ids],
        )


#: A field is a load transfer surface only when its corners lie in one plane
#: (RFEM's GEOMETRY_PLANE); farther out of plane than this (m) it stays member loads.
PLANARITY_TOLERANCE = 0.005


def _out_of_plane(points):
    """Largest distance of the points from the plane through the first three not collinear."""
    if len(points) < 4:
        return 0.0
    p0 = points[0]
    normal = None
    for i in range(1, len(points)):
        for j in range(i + 1, len(points)):
            u = [points[i][k] - p0[k] for k in range(3)]
            v = [points[j][k] - p0[k] for k in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(c * c for c in n))
            if length > 1e-9:
                normal = [c / length for c in n]
                break
        if normal:
            break
    if normal is None:
        return 0.0
    return max(abs(sum((p[k] - p0[k]) * normal[k] for k in range(3))) for p in points)


def _signed_area(a, b, c):
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def _fan_apex(plan):
    """A corner from which the fan of triangles covers the field (in plan) exactly, or None.

    Every triangle must turn the polygon's way and be more than a sliver - a
    corner in the middle of a straight side, or a concave corner seen from the
    wrong side, would give a degenerate or overlapping fan.
    """
    n = len(plan)
    total = sum(_signed_area(plan[0], plan[i], plan[i + 1]) for i in range(1, n - 1))
    if abs(total) < 1e-9:
        return None
    sign = 1.0 if total > 0 else -1.0
    minimum = 1e-4 * abs(total)
    for apex in range(n):
        order = [plan[(apex + i) % n] for i in range(n)]
        if all(sign * _signed_area(order[0], order[i], order[i + 1]) > minimum for i in range(1, n - 1)):
            return apex
    return None


class LoadTransferMapper:
    """Area loads as RFEM load transfer surfaces, one per loaded field.

    Runs after the members exist: a field's boundary must be the lines RFEM made
    for its members (a parallel line of its own would load nothing), and those
    numbers are only known once RFEM has created them. A field that is not
    planar - the roof follows the landscape - is fanned into triangles, each a
    plane; only a field that cannot be built so keeps member loads (the
    45-degree / centroid rule), so the total is kept either way.
    """

    def __init__(self, api, numbering, load_mapper):
        self.api = api
        self.numbering = numbering
        self.load_mapper = load_mapper
        self.report = {"surfaces": 0, "triangulated_fields": 0, "fields_as_member_loads": 0}

    def wanted(self, structural_model):
        return [a for a in getattr(structural_model, "area_loads", None) or [] if getattr(a, "transfer_surface", False)]

    def skipped_member_loads(self, structural_model):
        """Member load ids that the load transfer surfaces replace."""
        out = set()
        for area in self.wanted(structural_model):
            out.update(area.member_load_ids)
        return out

    def build(self, application, structural_model):
        """The surfaces and loads for every area load asking for one. Returns RFEM objects."""
        from compas_timber_fea.core.model import StructuralMemberLoad
        from compas.geometry import Vector

        areas = self.wanted(structural_model)
        if not areas:
            return []
        core = self.api.structure_core
        line_of = {m.no: m.line for m in application.get_object_list([core.Member()])}
        existing = [line.no for line in application.get_object_list([core.Line()])]
        self._next_line = max(existing + list(line_of.values()) + [0]) + 1
        points = {n.id: n.point for n in structural_model.nodes}

        surfaces_for = {}  # field key (sorted member ids) -> [(surface key, number)]
        objects, fallback = [], []
        for area in areas:
            numbers, keys = [], []
            for panel in area.panels:
                key = tuple(sorted(str(m) for m in panel["members"]))
                if key not in surfaces_for:
                    made = self._field_surfaces(panel, key, points, line_of, objects)
                    if made is None:
                        fallback.append((area, panel))
                        continue
                    surfaces_for[key] = made
                for surface_key, no in surfaces_for[key]:
                    numbers.append(no)
                    keys.append(surface_key)
            if numbers:
                objects.extend(self._surface_loads(area, keys[0], numbers))

        # The fields that stay member loads: their own share, by the same rule as before.
        for area, panel in fallback:
            self.report["fields_as_member_loads"] += 1
            widths, _ = edge_widths({"points": panel["points"], "edges": [tuple(e) for e in panel["edges"]]})
            p = area.pressure
            for (member_id, _a, _b), width in zip(panel["edges"], widths):
                load = StructuralMemberLoad(
                    id=0, member_id=member_id, load_case_id=area.load_case_id,
                    force=Vector(p[0] * width, p[1] * width, p[2] * width))
                objects.extend(self.load_mapper.map_member_load(load))
        return objects

    def _field_surfaces(self, panel, key, points, line_of, objects):
        """One plane load transfer surface for a planar field, triangles for a warped one.

        A warped field (the roof follows the landscape) is no plane, but any
        three of its corners are: it is fanned into triangles from a corner,
        the diagonals become free lines (no member, no stiffness) and each
        triangle hands its load to the members on its own edges. Returns
        ``[(surface key, number)]``, or None when the field cannot be built
        (a member without its line, a corner unknown, no valid fan).
        """
        members = panel["members"]
        corners = [points.get(n) for n in panel["nodes"]]
        lines = [line_of.get(self.numbering.member(m)) for m in members]
        if not all(lines) or not all(corners):
            return None
        coords = [[p.x, p.y, p.z] for p in corners]
        if _out_of_plane(coords) <= PLANARITY_TOLERANCE:
            no = self.numbering.surface(self._key(key))
            objects.append(self._surface(no, lines, [self.numbering.member(m) for m in members]))
            self.report["surfaces"] += 1
            return [(self._key(key), no)]

        apex = _fan_apex([[c[0], c[1]] for c in coords])
        if apex is None:
            return None
        n = len(coords)
        order = [(apex + i) % n for i in range(n)]  # corner indices from the apex on
        diagonal = {}
        for i in range(2, n - 1):
            diagonal[order[i]] = self._next_line
            objects.append(self.api.structure_core.Line(
                no=self._next_line,
                definition_nodes=[self.numbering.node(panel["nodes"][order[0]]),
                                  self.numbering.node(panel["nodes"][order[i]])],
                type="TYPE_POLYLINE",
            ))
            self._next_line += 1
        made = []
        for t in range(1, n - 1):
            a, b = order[t], order[t + 1]  # field edge a runs corner a -> corner b
            boundary, loaded = [lines[a]], [self.numbering.member(members[a])]
            if t == 1:
                boundary.insert(0, lines[order[0]])
                loaded.insert(0, self.numbering.member(members[order[0]]))
            else:
                boundary.insert(0, diagonal[a])
            if t == n - 2:
                boundary.append(lines[b])
                loaded.append(self.numbering.member(members[b]))
            else:
                boundary.append(diagonal[b])
            surface_key = "{}:t{}".format(self._key(key), t)
            no = self.numbering.surface(surface_key)
            objects.append(self._surface(no, boundary, loaded))
            self.report["surfaces"] += 1
            made.append((surface_key, no))
        self.report["triangulated_fields"] += 1
        return made

    def _surface(self, no, boundary_lines, loaded_members):
        S = self.api.structure_core.Surface
        enum = lambda field, name: S.DESCRIPTOR.fields_by_name[field].enum_type.values_by_name[name].number  # noqa: E731
        return S(
            no=no,
            type=enum("type", "TYPE_LOAD_TRANSFER"),
            geometry=enum("geometry", "GEOMETRY_PLANE"),
            boundary_lines=boundary_lines,
            load_transfer_direction=enum("load_transfer_direction", "LOAD_TRANSFER_DIRECTION_IN_BOTH"),
            load_distribution=enum("load_distribution", "LOAD_DISTRIBUTION_VARYING_LINEAR"),
            loaded_members=loaded_members,
            is_surface_weight_enabled=False,
        )

    @staticmethod
    def _key(field_key):
        return "load_transfer:" + ":".join(field_key)

    def _surface_loads(self, area, first_key, surface_numbers):
        """One surface load per pressure component on the area's surfaces (same convention as plates)."""
        from compas_timber_fea.core.model import StructuralSurfaceLoad

        load = StructuralSurfaceLoad(id=0, surface_id=self._key(first_key), load_case_id=area.load_case_id,
                                     pressure=area.pressure)
        out = []
        for obj in self.load_mapper.map_surface_load(load):
            del obj.surfaces[:]
            obj.surfaces.extend(surface_numbers)
            out.append(obj)
        return out
