import os

import compas

from compas.data import json_load

import compas_timber_fea
import compas_dlubal

# Configuration
from dotenv import load_dotenv
load_dotenv() # Loads variables from .env into environment

MY_API_KEY = os.getenv("DLUBAL_API_KEY")
APP_TYPE = "rfem" # or "rstab"

HERE = os.path.dirname(__file__)

TIMBER_MODEL_PATH = os.path.join(HERE, "timber_model_sticks.json")

# =================================================
# ============= MAIN EXECUTION BLOCK ==============

print(f"Loading timber model from: {TIMBER_MODEL_PATH}")
timber_model = json_load(TIMBER_MODEL_PATH)

# 1. TRANSLATION STEP (Timber -> Intermediate Model)
print("Translating timber model to agnostic structural model...")
from compas_timber_fea.translator import TimberToStructural

translator = TimberToStructural(connector_mode="rigid", material_name="C24")
structural_model = translator.translate(timber_model)

print(f"  -> Generated {len(structural_model.nodes)} structural nodes.")
print(f"  -> Generated {len(structural_model.members)} structural members.")

# 2. PUSH STEP (Intermediate Model -> Dlubal)
print("Initiating Live push to Dlubal...")
from compas_dlubal.dlubal.importer import DlubalImporter

export_success = False

try:
    importer = DlubalImporter(app_type=APP_TYPE, delete_all=True, api_key=MY_API_KEY, load_cases=["sw", "snow"])
    importer.run(structural_model, model_name="roundtrip-test-model")
    export_success = True
    print("Successfully exported to Dlubal!")

except Exception as e:
    print(f"Live export failed: {e}")

# 3. RESULT READBACK SCAFFOLD (Dlubal -> Intermediate Model)
if export_success:
    print("Reading Dlubal analysis results into agnostic result sets...")
    from compas_dlubal.dlubal.result_reader import DlubalResultReader

    try:
        result_reader = DlubalResultReader(app_type=APP_TYPE, api_key=MY_API_KEY)
        structural_model.results = result_reader.read(load_cases=[1, 3], calculate=True)

        print(f"  -> Generated {len(structural_model.results)} structural result sets.")
        for load_case_id, result_set in structural_model.results.items():
            print(
                f"  -> LC {load_case_id}: "
                f"{len(result_set.node_results)} node results, "
                f"{sum(len(values) for values in result_set.member_results.values())} member result samples, "
                f"{sum(len(values) for values in result_set.surface_results.values())} surface result samples."
            )

        first_result_set = next(iter(structural_model.results.values()), None)
        if first_result_set:
            likely_modules = first_result_set.metadata.get("inspection", {}).get("likely_result_modules", [])
            print(f"  -> Dlubal result-related API modules discovered: {likely_modules}")

    except Exception as e:
        print(f"Result readback scaffold failed: {e}")

# 4. NEXT ROUNDTRIP STEP
# Once concrete Dlubal result table mappings are implemented, map
# structural_model.results back to timber_model beam/plate attributes here.
