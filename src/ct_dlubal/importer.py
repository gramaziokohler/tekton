from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from compas.geometry import Point, Vector, Frame
from .mapping import DlubalMapper
from .utils import calculate_dlubal_rotation, NodeManager

logger = logging.getLogger(__name__)


class DlubalImporter:
    """
    Scaffolding for COMPAS Timber to Dlubal RSTAB/RFEM Importer.
    """

    def __init__(
        self,
        app_type: str = "rstab",
        api_key: Optional[str] = None,
        mapper: Optional[DlubalMapper] = None,
    ):
        """Initialize the importer with target application and optional mapping."""
        self.app_type = app_type.lower()
        self.api_key = api_key
        self.mapper = mapper or DlubalMapper()
        self.node_manager = NodeManager()
        self.api = None
        self._materials = {}
        self._sections = {}
        self.email = None
        self.password = None

    def _get_mat_no(self, name: str) -> int:
        if name not in self._materials:
            self._materials[name] = len(self._materials) + 1
        return self._materials[name]

    def _get_sec_no(self, name: str, mat_no: int) -> int:
        key = (name, mat_no)
        if key not in self._sections:
            self._sections[key] = len(self._sections) + 1
        return self._sections[key]

    def run(self, structural_model: Any, model_name: str = "Import", email: Optional[str] = None, password: Optional[str] = None):
        """Main entry point for the import process."""
        self.email = email
        self.password = password
        
        # 2. Gather data BEFORE connecting to Dlubal
        print("Gathering model data from COMPAS...")
        self._materials = {}
        self._sections = {}
        self.node_manager = NodeManager()
        members_data = []

        # COMPAS Timber 2.0: Get segments for each beam individually
        beams_data = {}
        if hasattr(structural_model, "beams"):
            found_beams = list(structural_model.beams)
            print("DEBUG: Processing beams...")
            for beam in found_beams:
                try:
                    segments = structural_model.get_beam_structural_segments(beam)
                    if segments:
                        beams_data[beam.guid] = segments
                except Exception as e:
                    pass
            
            print(f"DEBUG: Total beams with structural segments: {len(beams_data)}")

        connector_segments = []
        if hasattr(structural_model, "get_structural_connector_segments"):
            try:
                connector_segments = structural_model.get_structural_connector_segments()
            except Exception:
                pass

        # Process Beams
        if beams_data:
            beam_lookup = {str(b.guid): b for b in structural_model.beams}
            for beam_guid, segments in beams_data.items():
                parent_beam = beam_lookup.get(str(beam_guid))
                if not parent_beam: continue
                for segment in segments:
                    mat_name = self.mapper.map_material(segment.attributes.get("material") or "Timber")
                    mat_no = self._get_mat_no(mat_name)
                    cs_name = self.mapper.map_cross_section(segment.attributes.get("cross_section") or "Unknown")
                    cs_no = self._get_sec_no(cs_name, mat_no)
                    n1 = self.node_manager.get_node_number(segment.segment.start)
                    n2 = self.node_manager.get_node_number(segment.segment.end)
                    beta = calculate_dlubal_rotation(segment.frame)
                    members_data.append({"nodes": [n1, n2], "section": cs_no, "rotation": beta, "is_rigid": False})

        # Process Connectors
        for segment in connector_segments:
            n1 = self.node_manager.get_node_number(segment.segment.start)
            n2 = self.node_manager.get_node_number(segment.segment.end)
            members_data.append({"nodes": [n1, n2], "is_rigid": True})

        # 3. Connect to Dlubal via Port 9000
        print("Connecting to Dlubal via Port 9000 (gRPC Endpoint)...")
        import grpc
        from dlubal.api.rfem.application_pb2_grpc import ApplicationStub
        from google.protobuf.empty_pb2 import Empty

        # Build Authentication Metadata
        auth_metadata = []
        if self.email and self.password:
            print(f"DEBUG: Using Email Authentication: {self.email}")
            auth_metadata = [("email", str(self.email)), ("password", str(self.password))]
        else:
            effective_key = self.api_key or os.environ.get("DLUBAL_API_KEY") or "None"
            print(f"DEBUG: Using API Key: {effective_key}")
            auth_metadata = [("x-api-key", str(effective_key))]

        channel = grpc.insecure_channel("127.0.0.1:9000")
        stub = ApplicationStub(channel)
        
        try:
            print(f"DEBUG: Requesting active model...")
            active_model = stub.get_active_model(Empty(), metadata=auth_metadata)
            print(f"DEBUG: Targeted model SUCCESS: {active_model.name}")
        except Exception as e:
            print(f"DEBUG: AUTHENTICATION FAILED: {e}")
            channel.close()
            return

        try:
            from dlubal.api.rfem.structure_core.node_pb2 import Node
            from dlubal.api.rfem.structure_core.material_pb2 import Material
            from dlubal.api.rfem.structure_core.section_pb2 import Section
            from dlubal.api.rfem.structure_core.member_pb2 import Member
            from dlubal.api.rfem.application import pack_object

            def push(obj):
                try:
                    stub.create_object_impl(pack_object(obj), metadata=auth_metadata)
                    return True
                except Exception as e:
                    if "ALREADY_EXISTS" in str(e): return True
                    return False

            print(f"INJECTING {len(self.node_manager.nodes)} nodes...")
            for no, pt in self.node_manager.nodes.items():
                n = Node(no=int(no), coordinate_1=float(pt.x), coordinate_2=float(pt.y), coordinate_3=float(pt.z))
                push(n)

            for name, no in self._materials.items():
                push(Material(no=int(no), name=str(name)))

            for (name, mat_no), no in self._sections.items():
                push(Section(no=int(no), name=str(name), material=int(mat_no)))

            print(f"INJECTING {len(members_data)} members...")
            for i, m in enumerate(members_data):
                no_m = i + 1
                if m.get("is_rigid"):
                    mem = Member(no=no_m, node_start=int(m['nodes'][0]), node_end=int(m['nodes'][1]), type=13)
                else:
                    mem = Member(no=no_m, node_start=int(m["nodes"][0]), node_end=int(m["nodes"][1]), 
                                 section_start=int(m["section"]), section_end=int(m["section"]),
                                 rotation_angle=float(m.get("rotation", 0)))
                push(mem)
            
            print("Injection completed successfully!")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            channel.close()
            print("DEBUG: gRPC Channel released.")
