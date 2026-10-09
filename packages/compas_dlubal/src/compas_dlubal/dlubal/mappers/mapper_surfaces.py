class SurfaceMapper:
    def __init__(self, Core, types_for_lines=None, numbering=None):
        self.Core = Core
        # Surfaces and the nodes their lines reference carry hash ids; the
        # thickness does not (its own dense counter), so it passes through.
        from compas_dlubal.dlubal.numbering import Numbering

        self.numbering = numbering or Numbering()
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
                    definition_nodes=[self.numbering.node(u), self.numbering.node(v)],
                    type="TYPE_POLYLINE"
                ))
                self._lines_map[key] = line_no
                self._line_id_counter += 1

            line_ids.append(self._lines_map[key])

        # Create surface
        surface_kwargs = dict(
            no=self.numbering.surface(structural_surface.id),
            boundary_lines=line_ids,
            thickness=structural_surface.thickness_id
        )
        # Anchor the source plate GUID in RFEM for cross-session traceability.
        if structural_surface.source_element_id:
            surface_kwargs["id_for_export_import"] = structural_surface.source_element_id
        objects.append(self.Core.Surface(**surface_kwargs))

        return objects

    def _line_between(self, u, v, objects=None):
        """The line joining two nodes, reusing one if it already exists.

        The reuse is the point. A line support drawn on its own line, parallel
        to the plate's edge, would hold nothing - the plate is attached to
        *its* line, not to the support's. Sharing the line is what makes the
        support act on the plate, the same invariant that makes two plates
        meet rather than merely touch.
        """
        key = tuple(sorted((u, v)))
        if key not in self._lines_map:
            line_no = self._line_id_counter
            line = self.Core.Line(
                no=line_no,
                definition_nodes=[self.numbering.node(u), self.numbering.node(v)],
                type="TYPE_POLYLINE",
            )
            self._lines_map[key] = line_no
            self._line_id_counter += 1
            if objects is not None:
                objects.append(line)
        return self._lines_map[key]

    def map_line_support(self, line_support, objects=None):
        """Map a support along an edge.

        RFEM's LineSupport takes the per-metre stiffnesses **directly** - which
        is why the neutral model stores kN/m per metre rather than per node.
        OpenSees has no line support and has to distribute them by tributary
        length; here there is nothing to convert.

        Parameters
        ----------
        line_support : :class:`StructuralLineSupport`
        objects : list, optional
            Collects any Line objects that had to be created. A support on a
            plate edge needs none, because the surface already made them.
        """
        if self.types_for_lines is None:
            raise AttributeError("SurfaceMapper needs types_for_lines to create line supports")

        nodes = list(line_support.nodes or [])
        if len(nodes) < 2:
            raise ValueError(
                "line support {} has {} node(s); a line needs at least two".format(
                    line_support.id, len(nodes))
            )

        line_ids = [
            self._line_between(u, v, objects)
            for u, v in zip(nodes, nodes[1:])
        ]

        return self.types_for_lines.LineSupport(
            no=self.numbering.line_support(line_support.id),
            lines=line_ids,
            user_defined_name_enabled=True,
            name=line_support.name or "Line support",
            spring_x=line_support.ux,
            spring_y=line_support.uy,
            spring_z=line_support.uz,
            rotational_restraint_x=line_support.rx,
            rotational_restraint_y=line_support.ry,
            rotational_restraint_z=line_support.rz,
        )

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
