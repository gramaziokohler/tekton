from .dlubal.client import DlubalClient
from .dlubal.mappers.mapper_nodes import NodeMapper
from .dlubal.mappers.mapper_members import MemberMapper
from .dlubal.mappers.mapper_supports import SupportMapper
from .dlubal.mappers.mapper_loads import LoadMapper
from .translator import TimberToStructural

class TimberImporter:
    """Orchestrates the export from COMPAS Timber to structural software via a neutral model."""
    
    def __init__(self, app_type="rfem", api_key=None, delete_all=False, material_preset="C24", connector_mode="rigid"):
        self.app_type = app_type
        self.api_key = api_key
        self.delete_all = delete_all
        self.material_preset = material_preset
        self.connector_mode = connector_mode

    def run(self, timber_model, model_name="Import"):
        # 1. Translate to neutral model (Agnostic)
        translator = TimberToStructural(connector_mode=self.connector_mode, material_name=self.material_preset)
        structural_model = translator.translate(timber_model)
        
        # 2. Connect to Dlubal via Client Module
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

            # 3. Mapping from neutral -> Dlubal objects
            objects = []
            
            # Materials
            for mat_id, mat_name in structural_model.materials.items():
                objects.append(member_mapper.map_material(mat_id, mat_name))

            # Nodes
            for n in structural_model.nodes:
                objects.append(node_mapper.map(n))

            # Sections
            for s in structural_model.sections:
                objects.append(member_mapper.map_section(s))

            # Members
            for m in structural_model.members:
                objects.append(member_mapper.map_member(m))

            # Supports
            for su in structural_model.supports:
                objects.append(support_mapper.map(su))

            # Loads
            objects.extend(load_mapper.default_load_case())

            # 4. Push to Dlubal
            try:
                conn.create_object_list(objects)
                print(f"Successfully exported {len(objects)} objects to Dlubal.")
                return True
            except Exception as e:
                print(f"Export error: {e}")
                raise

