from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from compas.geometry import Point, Vector

from compas_timber_fea.core.releases import LoadCombination
from compas_timber_fea.core.releases import MemberEccentricity
from compas_timber_fea.core.releases import MemberRelease

@dataclass
class StructuralNode:
    id: int
    point: Point
    source_element_id: Optional[str] = None
    source_element_type: Optional[str] = None
    source_node_id: Optional[str] = None

@dataclass
class StructuralThickness:
    id: int
    name: str # e.g. "Thickness 0.12m"
    material_id: int
    thickness: float = 0.0 # in meters

@dataclass
class StructuralSurface:
    id: int
    nodes: List[int]
    thickness_id: int
    # Closed rings of node ids that are *not* part of the surface - windows,
    # doors, service penetrations. First-class rather than a boolean result:
    # an opening changes how a plate spans, and every serious target format
    # carries it as its own loop (RFEM opening object, IFC inner boundary,
    # SAF opening). Subtracting it into the outline would destroy that and
    # the plate's identity with it.
    openings: List[List[int]] = field(default_factory=list)
    # Direction of the strong axis, in global coordinates. Timber panels (CLT,
    # sheathing) are markedly stiffer along the grain of their face layers, so
    # a surface without this is only meaningful if it is genuinely isotropic.
    span_direction: Optional[Vector] = None
    source_element_id: Optional[str] = None
    source_element_type: Optional[str] = None
    source_surface_id: Optional[str] = None

@dataclass
class StructuralSurfaceConnection:
    id: int
    nodes: List[int]
    # Mechanical behaviour along the shared edge (inf = continuous, 0 = released,
    # finite = spring), in the same convention as StructuralSupport.
    release: Optional[MemberRelease] = None
    source_joint_id: Optional[str] = None
    # Source plates on either side of the edge, for traceability.
    source_element_ids: List[str] = field(default_factory=list)

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
    # Mechanical end conditions. None means fully continuous; a MemberRelease
    # carries per-DOF stiffness (inf = rigid, 0 = free, finite = spring).
    release_start: Optional[MemberRelease] = None
    release_end: Optional[MemberRelease] = None
    # Offset of the member axis from the system line, in local axes.
    eccentricity: Optional[MemberEccentricity] = None
    source_element_id: Optional[str] = None
    source_element_type: Optional[str] = None
    source_segment_id: Optional[str] = None
    # Which timber joint produced each end condition, for traceability.
    source_joint_start: Optional[str] = None
    source_joint_end: Optional[str] = None

@dataclass
class StructuralNodeResult:
    node_id: int
    load_case_id: int
    displacement: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # m
    rotation: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # rad
    reaction_force: Optional[Vector] = None # kN, the force the support exerts ON the structure (a pinned foot under gravity: +z)
    reaction_moment: Optional[Vector] = None # kNm, same convention
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StructuralMemberResult:
    member_id: int
    load_case_id: int
    position: float = 0.0 # relative 0.0-1.0 along member
    axial: float = 0.0 # kN
    shear_y: float = 0.0 # kN
    shear_z: float = 0.0 # kN
    torsion: float = 0.0 # kNm
    moment_y: float = 0.0 # kNm
    moment_z: float = 0.0 # kNm
    displacement: Optional[Vector] = None # m
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StructuralSurfaceResult:
    surface_id: int
    load_case_id: int
    position: Optional[Point] = None
    membrane_force_x: float = 0.0 # kN/m
    membrane_force_y: float = 0.0 # kN/m
    membrane_force_xy: float = 0.0 # kN/m
    moment_x: float = 0.0 # kNm/m
    moment_y: float = 0.0 # kNm/m
    moment_xy: float = 0.0 # kNm/m
    displacement: Optional[Vector] = None # m
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StructuralResultSet:
    load_case_id: int
    name: str = ""
    node_results: Dict[int, StructuralNodeResult] = field(default_factory=dict)
    member_results: Dict[int, List[StructuralMemberResult]] = field(default_factory=dict)
    surface_results: Dict[int, List[StructuralSurfaceResult]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

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
class StructuralLineSupport:
    """A support along an edge - a wall foot, a slab bearing on a wall.

    Separate from :class:`StructuralSupport` because the stiffnesses mean
    something different: a nodal spring is kN/m, a line spring is **kN/m per
    metre of length** (kN/m2). Putting both in one class behind a flag would
    make six fields whose unit depends on another field - the same silent
    ambiguity that once let two timber grades share one section.

    The line is a chain of node ids, in order. Sharing the node ids with the
    surface outline is what makes the support conform to the mesh: the plate
    and its support meet on the same nodes by construction rather than by
    coordinate luck.

    How a backend realises it is its own business. OpenSees has no line
    support, so the adapter distributes the stiffness over the chain by
    tributary length; RFEM has a native LineSupport object and takes the
    per-metre values directly.
    """
    id: int
    #: Node ids along the line, in order. Two or more.
    nodes: List[int]
    name: str = "Line support"
    #: Translational stiffness in kN/m2 (kN/m per metre of line). inf = rigid.
    ux: float = float('inf')
    uy: float = float('inf')
    uz: float = float('inf')
    #: Rotational stiffness in kNm/m per radian. inf = rigid.
    rx: float = float('inf')
    ry: float = float('inf')
    rz: float = float('inf')
    #: Which plate edge this came from, for traceability and for the
    #: engineer's report.
    source_element_id: Optional[str] = None
    source_edge_index: Optional[int] = None

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
class StructuralSurfaceLoad:
    """A pressure on a plate, in kN/m2.

    The load belongs to the plate, not to its mesh: how finely a backend
    tessellates is its own business, and the load has to survive a change of
    mesh density unchanged. Adapters distribute it over whatever elements
    they built.
    """
    id: int
    surface_id: int
    load_case_id: int
    pressure: Vector = field(default_factory=lambda: Vector(0, 0, 0)) # kN/m2
    #: True = the pressure acts along the plate normal (snow on a pitched
    #: roof is given per m2 of *plan* area, not of surface area).
    projected: bool = False

@dataclass
class StructuralModel:
    nodes: List[StructuralNode] = field(default_factory=list)
    members: List[StructuralMember] = field(default_factory=list)
    sections: List[StructuralSection] = field(default_factory=list)
    supports: List[StructuralSupport] = field(default_factory=list)
    line_supports: List[StructuralLineSupport] = field(default_factory=list)
    # Values are Material objects carrying real physical properties (see
    # core/materials.py); plain grade-name strings from older serialized
    # models still load and are upgraded by consumers via Material.resolve.
    materials: Dict[int, Any] = field(default_factory=dict)
    load_cases: List[StructuralLoadCase] = field(default_factory=list)
    load_combinations: List[LoadCombination] = field(default_factory=list)
    point_loads: List[StructuralPointLoad] = field(default_factory=list)
    member_loads: List[StructuralMemberLoad] = field(default_factory=list)
    surface_loads: List[StructuralSurfaceLoad] = field(default_factory=list)
    thicknesses: List[StructuralThickness] = field(default_factory=list)
    surfaces: List[StructuralSurface] = field(default_factory=list)
    surface_connections: List[StructuralSurfaceConnection] = field(default_factory=list)
    results: Dict[int, StructuralResultSet] = field(default_factory=dict)
    # Everything in the neutral model is SI: metres, kN, kNm. The source model's
    # unit is recorded so a translation can state what it converted from.
    source_units: str = "m"

    def to_json(self, filepath, pretty=True):
        """Serialise the model to JSON. See :mod:`compas_timber_fea.core.serialization`."""
        from compas_timber_fea.core.serialization import model_to_json

        return model_to_json(self, filepath, pretty=pretty)

    @classmethod
    def from_json(cls, filepath):
        """Load a model previously written with :meth:`to_json`."""
        from compas_timber_fea.core.serialization import model_from_json

        return model_from_json(filepath)
