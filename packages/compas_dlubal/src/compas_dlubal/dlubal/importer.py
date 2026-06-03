from compas_dlubal.dlubal.client import DlubalClient
from compas_dlubal.dlubal.mappers.mapper_nodes import NodeMapper
from compas_dlubal.dlubal.mappers.mapper_members import MemberMapper
from compas_dlubal.dlubal.mappers.mapper_supports import SupportMapper
from compas_dlubal.dlubal.mappers.mapper_loads import LoadMapper
from compas_dlubal.dlubal.mappers.mapper_thicknesses import ThicknessMapper
from compas_dlubal.dlubal.mappers.mapper_surfaces import SurfaceMapper
# Translator removed here, handled upstream

class DlubalImporter:
    """Orchestrates the export from the neutral structural model to Dlubal via gRPC."""
    
    def __init__(self, app_type="rfem", api_key=None, delete_all=False, material_preset="C24", connector_mode="rigid", load_cases=["sw"]):
        self.app_type = app_type
        self.api_key = api_key
        self.delete_all = delete_all
        self.material_preset = material_preset
        self.connector_mode = connector_mode
        self.load_cases = load_cases

    def _remove_zero_length_members(self, structural_model, tol=1e-6):
        nodes_by_id = {node.id: node for node in structural_model.nodes}
        valid_members = []
        removed_member_ids = set()

        for member in structural_model.members:
            start_node = nodes_by_id.get(member.node_start)
            end_node = nodes_by_id.get(member.node_end)

            if not start_node or not end_node:
                valid_members.append(member)
                continue

            if start_node.point.distance_to_point(end_node.point) <= tol:
                removed_member_ids.add(member.id)
                continue

            valid_members.append(member)

        if removed_member_ids:
            structural_model.members = valid_members
            structural_model.member_loads = [load for load in structural_model.member_loads if load.member_id not in removed_member_ids]
            print(f"{len(removed_member_ids)} elements with 0 length removed.")

    def run(self, structural_model, model_name="Import"):
        self._remove_zero_length_members(structural_model)

        # 1. Connect to Dlubal via Client Module
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            if self.delete_all:
                conn.delete_all_objects()

            # Collect node coordinates for the MemberMapper
            nodes_cache = {n.id: n.point for n in structural_model.nodes}

            # Initialize Mappers (Software-specific)
            node_mapper = NodeMapper(conn.api.structure_core)
            member_mapper = MemberMapper(conn.api.structure_core, nodes_cache=nodes_cache)
            support_mapper = SupportMapper(conn.api.types_for_nodes)
            load_mapper = LoadMapper(conn.api.loading)
            thickness_mapper = ThicknessMapper(conn.api.structure_core)
            surface_mapper = SurfaceMapper(conn.api.structure_core)

            # 3. Mapping from neutral -> Dlubal objects
            objects = []
            
            # Materials
            for mat_id, mat_name in structural_model.materials.items():
                objects.append(member_mapper.map_material(mat_id, mat_name))

            # Nodes
            for n in structural_model.nodes:
                objects.append(node_mapper.map(n))

            # Thicknesses
            for t in structural_model.thicknesses:
                objects.append(thickness_mapper.map(t))

            # Sections
            for s in structural_model.sections:
                objects.append(member_mapper.map_section(s))

            # Members
            for m in structural_model.members:
                objects.append(member_mapper.map_member(m))

            # Surfaces
            for su in structural_model.surfaces:
                objects.extend(surface_mapper.map(su))

            # Supports
            for su in structural_model.supports:
                objects.append(support_mapper.map(su))

            # Loads (using selected cases)
            objects.extend(load_mapper.create_load_cases(self.load_cases))

            # 4. Push to Dlubal
            try:
                conn.create_object_list(objects)
                print(f"Successfully exported {len(objects)} objects to Dlubal.")
                return True
            except Exception as e:
                print(f"Export error: {e}")
                raise

