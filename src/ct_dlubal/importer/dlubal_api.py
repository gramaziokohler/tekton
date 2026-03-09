from .dlubal.client import DlubalClient
from .dlubal.mapper_nodes import NodeMapper
from .dlubal.mapper_members import MemberMapper
from .dlubal.mapper_supports import SupportMapper
from .dlubal.mapper_loads import LoadMapper

class LiveImporter:
    """Importer for direct gRPC communication with Dlubal RFEM."""
    
    def __init__(self, model, app_type="rfem", api_key=None, delete_all=False):
        """Initialize the LiveImporter.
        
        Parameters
        ----------
        model : StructuralModel
            The structural model to be pushed.
        app_type : str, optional
            The Dlubal application type ("rfem" or "rstab"). Default is "rfem".
        api_key : str, optional
            The API key for Dlubal. Default is None.
        delete_all : bool, optional
            Whether to delete all existing objects in the model before pushing. Default is False.
        """
        self.model = model
        self.app_type = app_type
        self.api_key = api_key
        self.delete_all = delete_all

    def push_to_dlubal(self):
        """Push the structural model to a running instance of Dlubal via gRPC."""
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            if self.delete_all:
                conn.delete_all_objects()

            # Prepare mapping context
            nodes_cache = {n.id: n.point for n in self.model.nodes}
            node_mapper = NodeMapper(conn.api.structure_core)
            member_mapper = MemberMapper(conn.api.structure_core, nodes_cache=nodes_cache)
            support_mapper = SupportMapper(conn.api.types_for_nodes)
            load_mapper = LoadMapper(conn.api.loading)

            # Map the neutral model to Dlubal objects
            objects = []
            
            # 1. Materials
            for mat_id, mat_name in self.model.materials.items():
                objects.append(member_mapper.map_material(mat_id, mat_name))

            # 2. Nodes
            for n in self.model.nodes:
                objects.append(node_mapper.map(n))

            # 3. Sections
            for s in self.model.sections:
                objects.append(member_mapper.map_section(s))

            # 4. Members
            for m in self.model.members:
                objects.append(member_mapper.map_member(m))

            # 5. Supports
            for su in self.model.supports:
                objects.append(support_mapper.map(su))

            # 6. Default Load Case
            objects.extend(load_mapper.default_load_case())

            # Push everything to the application
            try:
                conn.create_object_list(objects)
                print(f"Successfully exported {len(objects)} objects to {self.app_type.upper()}.")
                return True
            except Exception as e:
                print(f"Failed to export: {e}")
                raise
