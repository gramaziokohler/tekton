from dataclasses import dataclass, field
from typing import List, Optional, Dict
from compas.geometry import Point, Frame, Vector

@dataclass
class StructuralNode:
    id: int
    point: Point

@dataclass
class StructuralSection:
    id: int
    name: str # e.g. "RECT 120/240" (optional, fallback)
    material_id: int
    width: float = 0.0 # in meters (standard COMPAS/SI)
    height: float = 0.0 # in meters
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
    member_type: str = "BEAM" # "BEAM", "RIGID", "COUPLING"

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
class StructuralLoadCase:
    id: int
    name: str
    action_category: str = "PERMANENT" # "PERMANENT", "VARIABLE", "SNOW", "WIND"
    self_weight: bool = False

@dataclass
class StructuralPointLoad:
    id: int
    node_id: int
    load_case_id: int
    force: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # in kN
    moment: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # in kNm

@dataclass
class StructuralMemberLoad:
    id: int
    member_id: int
    load_case_id: int
    force: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # kN/m
    dist_start: float = 0.0 # relative 0.0-1.0 or absolute
    dist_end: float = 1.0

@dataclass
class StructuralModel:
    nodes: List[StructuralNode] = field(default_factory=list)
    members: List[StructuralMember] = field(default_factory=list)
    sections: List[StructuralSection] = field(default_factory=list)
    supports: List[StructuralSupport] = field(default_factory=list)
    materials: Dict[int, str] = field(default_factory=dict)
    load_cases: List[StructuralLoadCase] = field(default_factory=list)
    point_loads: List[StructuralPointLoad] = field(default_factory=list)
    member_loads: List[StructuralMemberLoad] = field(default_factory=list)
