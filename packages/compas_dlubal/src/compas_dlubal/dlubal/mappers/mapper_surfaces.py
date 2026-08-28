class SurfaceMapper:
    def __init__(self, Core, types_for_lines=None):
        self.Core = Core
        # LineHinge lives in a different proto module than the structure core.
        self.types_for_lines = types_for_lines
        self._line_id_counter = 1000 # Offset for border lines
        self._lines_map = {} # (u, v) -> line_id
        self._hinge_id_counter = 1
        self._hinges_map = {}

    def map(self, structural_surface):
        """Maps StructuralSurface to Dlubal Surface.
        
        Returns a list: [Line1, Line2, ..., Surface]
        """
        objects = []
        line_ids = []
        node_ids = structural_surface.nodes
        
        # Create boundary lines
        for i in range(len(node_ids)):
            u = node_ids[i]
            v = node_ids[(i + 1) % len(node_ids)]
            
            # Sort node IDs to identify the same edge regardless of direction
            key = tuple(sorted((u, v)))
            
            if key not in self._lines_map:
                line_no = self._line_id_counter
                objects.append(self.Core.Line(
                    no=line_no,
                    definition_nodes=[u, v],
                    type="TYPE_POLYLINE"
                ))
                self._lines_map[key] = line_no
                self._line_id_counter += 1

            line_ids.append(self._lines_map[key])

        # Create surface
        surface_kwargs = dict(
            no=structural_surface.id,
            boundary_lines=line_ids,
            thickness=structural_surface.thickness_id
        )
        # Anchor the source plate GUID in RFEM for cross-session traceability.
        if structural_surface.source_element_id:
            surface_kwargs["id_for_export_import"] = structural_surface.source_element_id
        objects.append(self.Core.Surface(**surface_kwargs))

        return objects

    def map_connections(self, surface_connections):
        """Map plate-to-plate edge connections to Dlubal LineHinge objects.

        Connections sharing the same release share one hinge, which is assigned
        to every line it applies to - the way an engineer defines an edge type
        once. Continuous connections need no object, since a line is continuous
        by default.

        Note the reduced vocabulary: a LineHinge releases three translations and
        rotation about the edge axis only. A neutral release that frees bending
        about the other two axes has no equivalent along an edge, so only the
        components listed below survive the translation.
        """
        if self.types_for_lines is None:
            raise AttributeError("SurfaceMapper needs types_for_lines to create line hinges")

        lines_by_release = {}
        for connection in surface_connections:
            release = connection.release
            if release is None or release.is_rigid():
                continue

            line_no = self._lines_map.get(tuple(sorted(connection.nodes)))
            if line_no is None:
                # The edge belongs to a surface that was never mapped, so there
                # is no line to attach a hinge to.
                continue

            key = tuple(getattr(release, dof) for dof in ("ux", "uy", "uz", "rx"))
            lines_by_release.setdefault(key, (release, []))[1].append(line_no)

        objects = []
        for key, (release, line_numbers) in lines_by_release.items():
            hinge_no = self._hinge_id_counter
            objects.append(self.types_for_lines.LineHinge(
                no=hinge_no,
                name=release.name or f"Plate edge {hinge_no}",
                translational_release_u_x=float(release.ux),
                translational_release_u_y=float(release.uy),
                translational_release_u_z=float(release.uz),
                rotational_release_phi_x=float(release.rx),
                assigned_to=",".join(str(no) for no in sorted(set(line_numbers))),
            ))
            self._hinges_map[key] = hinge_no
            self._hinge_id_counter += 1

        return objects
