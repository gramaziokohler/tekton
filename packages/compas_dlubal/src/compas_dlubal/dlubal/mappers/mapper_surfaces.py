class SurfaceMapper:
    def __init__(self, Core):
        self.Core = Core
        self._line_id_counter = 1000 # Offset for border lines
        self._lines_map = {} # (u, v) -> line_id

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
                    definition_nodes=f"{u}, {v}",
                    type="TYPE_POLYLINE"
                ))
                self._lines_map[key] = line_no
                self._line_id_counter += 1
            
            line_ids.append(self._lines_map[key])
            
        boundary_lines_str = ", ".join(map(str, line_ids))
        
        # Create surface
        objects.append(self.Core.Surface(
            no=structural_surface.id,
            boundary_lines=boundary_lines_str,
            thickness=structural_surface.thickness_id
        ))
        
        return objects
