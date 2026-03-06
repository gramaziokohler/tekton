
from typing import Union, List
from unittest.main import main

from compas.datastructures.mesh.mesh import Mesh
from compas.geometry import is_colinear_line_line
from compas.geometry import Line, Vector
from compas.geometry import Transformation

from compas_timber.connections import JointTopology, LMiterJoint, TButtJoint, XLapJoint
# from compas_timber.design import DirectRule, JointRuleSolver, TopologyRule, CategoryRule
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from a03_multi_surface_setup import MultiFaceRFSystem
from a03_rf_system import RFSystem


class TimberModelCreator:
    """
    Creates a unique COMPAS Timber Model from a list of `RFSystem` objects.
    """

    def __init__(self, rf_system: RFSystem, beam_width: float = 0.08, beam_height: float = 0.10):
        self.rf_systems = rf_system
        self.timber_model = TimberModel()
        self.beam_width = beam_width
        self.beam_height = beam_height
        self._rules = []
        self.tol = 0.2


    def _create_beams(self) -> None:
        for rf_system in self.rf_systems:
            mesh: Mesh = rf_system.mesh
            for edge in mesh.edges():
                centerline = mesh.edge_attribute(edge, "centerline")
                z_vector = None

                surface = rf_system.target_surface
                if surface:
                    # Do not use modulo `% 1.0` on surface parameters.
                    # Surface domains are not necessarily normalized 0 to 1.
                    point, (u, v) = surface.closest_point(centerline.midpoint, return_parameters=True)
                    frame = surface.frame_at(u, v)

                    # The z_vector defines the height direction of the cross-section.
                    # Setting it to the surface normal aligns the beam correctly.
                    z_vector = frame.zaxis
                    # z_vector = Vector(0, 0, 1)  # For testing, use global z-axis to check if rotation is applied correctly

                beam = Beam.from_centerline(centerline, width=self.beam_width, height=self.beam_height, z_vector=z_vector)

                self.timber_model.add_element(beam)
                mesh.edge_attribute(edge, "beam", beam)
   
    # =============================================================
    # ---------------- Direct Topological approach ----------------

    def create_timber_model_topological(self, process_joinery: bool = False) -> TimberModel:
        self._create_beams()
        self._implement_joints_direct()
        self._implement_boundary_joints_direct()
        
        if process_joinery:
            self.timber_model.process_joinery()
        return self.timber_model

    def _implement_joints_direct(self) -> None:
        for rf_system in self.rf_systems:
            mesh: Mesh = rf_system.mesh
            for edge in mesh.edges():
                if mesh.is_edge_on_boundary(edge):
                    continue

                beam = mesh.edge_attribute(edge, "beam")
                next_edge = mesh.edge_attribute(edge, "next_edge")
                prev_edge = mesh.edge_attribute(edge, "prev_edge")
                
                next_beam = mesh.edge_attribute(next_edge, "beam") if next_edge else None
                prev_beam = mesh.edge_attribute(prev_edge, "beam") if prev_edge else None

                if not beam:
                    continue

                # Logik für Übergang Innen -> Rand (T-Stöße)
                if next_edge and mesh.is_edge_on_boundary(next_edge):
                    if next_beam:
                        self.timber_model.add_joint(TButtJoint(beam, next_beam))
                    if prev_beam:
                        self.timber_model.add_joint(XLapJoint(prev_beam, beam))
                    continue
                
                if prev_edge and mesh.is_edge_on_boundary(prev_edge):
                    if prev_beam:
                        self.timber_model.add_joint(TButtJoint(beam, prev_beam))
                    if next_beam:
                        self.timber_model.add_joint(XLapJoint(next_beam, beam))
                    continue

                # Standard Innenverbindungen (Überblattungen)
                if next_beam:
                    self.timber_model.add_joint(XLapJoint(next_beam, beam))
                if prev_beam:
                    self.timber_model.add_joint(XLapJoint(prev_beam, beam))

    def _implement_boundary_joints_direct(self) -> None:
        for rf_system in self.rf_systems:
            mesh: Mesh = rf_system.mesh
            for v in mesh.vertices_on_boundary():
                b_edges = [e for e in mesh.vertex_edges(v) if mesh.is_edge_on_boundary(e)]
                if len(b_edges) == 2:
                    beam_a = mesh.edge_attribute(b_edges[0], "beam")
                    beam_b = mesh.edge_attribute(b_edges[1], "beam")
                    if beam_a and beam_b:
                        self.timber_model.add_joint(LMiterJoint(beam_a, beam_b))

    # =============================================================
    # ---------------- Refined Rule-based approach ----------------

    # copy from a01_timber_model.py
