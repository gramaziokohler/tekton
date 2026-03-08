from dataclasses import dataclass, field
from typing import List, Optional, Dict
from compas.geometry import Point, Frame

@dataclass
class StructuralNode:
    id: int
    point: Point

@dataclass
class StructuralSection:
    id: int
    name: str # e.g. "RECT 120/240" (optional, fallback)
    width: float = 0.0 # in meters (standard COMPAS/SI)
    height: float = 0.0 # in meters
    material_id: int
    shape_type: str = "rectangular" # "rectangular", "circular", etc.

@dataclass
class StructuralMember:
    id: int
    node_start: int
    node_end: int
    section_id: int
    # A vector defining the local "up" or "side" orientation (agnostic)
    # Typically the Y-axis of the beam's frame in COMPAS
    orientation_vector: Vector = field(default_factory=lambda: Vector(0, 0, 1))
    is_rigid: bool = False

@dataclass
class StructuralSupport:
    id: int
    nodes: List[int]
    name: str = "Support"
    # inf means rigid
    ux: float = float('inf')
    uy: float = float('inf')
    uz: float = float('inf')
    rx: float = float('inf')
    ry: float = float('inf')
    rz: float = float('inf')

@dataclass
class StructuralModel:
    nodes: List[StructuralNode] = field(default_factory=list)
    members: List[StructuralMember] = field(default_factory=list)
    sections: List[StructuralSection] = field(default_factory=list)
    supports: List[StructuralSupport] = field(default_factory=list)
    materials: Dict[int, str] = field(default_factory=dict)
