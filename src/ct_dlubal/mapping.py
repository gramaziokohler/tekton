from __future__ import annotations

from typing import Dict
from typing import Optional


class DlubalMapper:
    """
    Scaffold for mapping COMPAS Timber attributes to Dlubal database entries.
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
        return self.material_map.get(compas_material, compas_material)

    def map_cross_section(self, compas_cs: Optional[str]) -> str:
        """Map a COMPAS section (e.g., 160x160) to a Dlubal library string."""
        # TODO: Heuristic for standard timber nomenclature.
        return self.cross_section_map.get(compas_cs, compas_cs)
