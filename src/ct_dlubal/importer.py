
from .utils import NodeManager, calculate_dlubal_rotation
from .translator import TimberToStructural
from .backends.dlubal.mapper import DlubalMapper

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
        # 1. Übersetzen in neutrales Modell
        translator = TimberToStructural(connector_mode=self.connector_mode, material_name=self.material_preset)
        structural_model = translator.translate(timber_model)
        
        # 2. Verbinden mit Dlubal API
        if self.app_type.lower() == "rstab":
            from dlubal.api import rstab as dlubal_api
        else:
            from dlubal.api import rfem as dlubal_api
            
        AppClass = dlubal_api.Application
        Core = dlubal_api.structure_core
        TFN = dlubal_api.types_for_nodes
        Loc = dlubal_api.loading

        with AppClass(api_key_value=self.api_key) as app:
            if self.delete_all:
                app.delete_all_objects()

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

