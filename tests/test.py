import sys
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

try:
    importer = DlubalImporter(app_type=APP_TYPE, delete_all=True, api_key=MY_API_KEY, load_cases=["sw", "snow"])
    importer.run(structural_model, model_name="test-model")
    print("Successfully exported to Dlubal!")

except Exception as e:
    print(f"Live export failed: {e}")

# 3. (OPTIONAL) SAVE STEP
# from compas_saf.exporter.saf import SAFExporter
# exporter = SAFExporter(structural_model)
# exporter.export(r"C:\path\to\output.saf")

