
from .utils import NodeManager, calculate_dlubal_rotation
from .translator import TimberToStructural
from .importer.dlubal.client import DlubalClient
from .importer.dlubal.mapper_nodes import NodeMapper
from .importer.dlubal.mapper_members import MemberMapper
from .importer.dlubal.mapper_supports import SupportMapper
from .importer.dlubal.mapper_loads import LoadMapper

class TimberImporter:
    """Orchestriert den Export von COMPAS Timber zu Statiksoftware über ein neutrales Modell"""
    def __init__(self, app_type="rfem", api_key=None, override_objects=True, delete_all=False, material_preset="C24", connector_mode="rigid"):
        self.app_type = app_type
        self.api_key = api_key
        self.override_objects = override_objects
        self.delete_all = delete_all
        self.material_preset = material_preset
        self.connector_mode = connector_mode

    def run(self, timber_model, model_name="Import"):
        # 1. Übersetzen in neutrales Modell (Agnostisch)
        translator = TimberToStructural(connector_mode=self.connector_mode, material_name=self.material_preset)
        structural_model = translator.translate(timber_model)
        
        # 2. Verbindung mit Dlubal über Client Modul
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            if self.delete_all:
                conn.delete_all_objects()

            # Knoten Koordinaten für den MemberMapper sammeln
            nodes_cache = {n.id: n.point for n in structural_model.nodes}

            # Mappers initialisieren (Software-spezifisch)
            node_mapper = NodeMapper(conn.api.structure_core)
            member_mapper = MemberMapper(conn.api.structure_core, nodes_cache=nodes_cache)
            support_mapper = SupportMapper(conn.api.types_for_nodes)
            load_mapper = LoadMapper(conn.api.loading)

            # 3. Mapping von neutral -> Dlubal PB Objekte
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

            # 4. Push zu Dlubal
            try:
                conn.create_object_list(objects)
                print(f"Erfolgreich {len(objects)} Objekte nach Dlubal exportiert.")
            except Exception as e:
                print(f"Fehler beim Export: {e}")
                raise

        if self.app_type.lower() == "rstab":
            from dlubal.api import rstab
            AppClass = rstab.Application
            Core = rstab.structure_core
            TFN = rstab.types_for_nodes
            Loc = rstab.loading
        else:
            from dlubal.api import rfem
            AppClass = rfem.Application
            Core = rfem.structure_core
            TFN = rfem.types_for_nodes
            Loc = rfem.loading

        # with statement automatically opens and CLOSES the connection safely
        with AppClass(api_key_value=self.api_key) as app:
            print("model connected successfully.")

            # implement optional delete all logic before starting
            if self.delete_all:
                print("DEBUG: parameter delete_all=True ... deleting all existing model objects...")
                try:
                    app.delete_all_objects()
                except Exception as e:
                    print(f"DEBUG: Could not execute delete_all_objects: {e}")
            
            print("DEBUG: preparing objects list in python...")
            
            # 3. Mapping von neutral -> Dlubal
            mapper = DlubalMapper(Core, TFN, Loc, material_name=self.material_preset)
            objects = mapper.map_model(structural_model)

            # 4. Push zu Dlubal
            try:
                app.create_object_list(objects)
                print(f"Erfolgreich {len(objects)} Objekte nach Dlubal exportiert.")
            except Exception as e:
                print(f"Fehler beim Export: {e}")
                raise

