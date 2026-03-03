from __future__ import annotations

from typing import Dict
from typing import Optional


class DlubalMapper:
    """
    Mapping COMPAS Timber attributes to Dlubal database entries.
    """

    def __init__(
        self,
        material_map: Optional[Dict[str, str]] = None,
        cross_section_map: Optional[Dict[str, str]] = None,
        default_material: str = "GL24h",
        default_cross_section: str = "Rect 160/320",
    ):
        """Pre-fills and manages common timber material/CS mappings."""
        self.material_map = material_map or {}
        self.cross_section_map = cross_section_map or {}
        self.default_material = default_material
        self.default_cross_section = default_cross_section

    def map_material(self, compas_material: Optional[str]) -> str:
        """Map a COMPAS material (e.g., C24) to a Dlubal library string."""
        if not compas_material:
            return self.default_material
        return self.material_map.get(compas_material, compas_material)

    def map_cross_section(self, compas_cs: Optional[str]) -> str:
        """Map a COMPAS section (e.g., 160x160) to a Dlubal library string."""
        if not compas_cs:
            return self.default_cross_section
        
        mapped = self.cross_section_map.get(compas_cs)
        if mapped:
            return mapped

        # "160x160" -> "Rect 160/160"
        if "x" in compas_cs.lower():
            parts = compas_cs.lower().split("x")
            if len(parts) == 2:
                try:
                    return f"Rect {int(float(parts[0]))}/{int(float(parts[1]))}"
                except ValueError:
                    pass
        return compas_cs

