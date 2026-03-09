import sys
import os

# Dev: Ensure local compas_timber and ct_dlubal are in path first
CT_SRC = r"C:\path\to\compas_timber\src"
DL_SRC = r"C:\path\to\ct_dlubal\src"

for p in [CT_SRC, DL_SRC]:
    if p not in sys.path:
        sys.path.insert(0, p)

import compas
from compas.data import json_load

# IMPORTANT: Ensure the Dlubal gRPC python package path is available
# (Adjust this path if the RFEM 6 bin folder is different)
sys.path.append(r"C:\Program Files\Dlubal\RSTAB 9.12\bin\Lib\site-packages")

import ct_dlubal

# Configuration
from dotenv import load_dotenv
load_dotenv() # Loads variables from .env into environment

MY_API_KEY = os.getenv("DLUBAL_API_KEY")
APP_TYPE = "rfem" # or "rstab"
TIMBER_MODEL_PATH = r"C:\path\to\ct_dlubal\tests\timber-models\timber_model-rotated-beams-2.json"

# =================================================
# ============= MAIN EXECUTION BLOCK ==============

print(f"Loading timber model from: {TIMBER_MODEL_PATH}")
timber_model = json_load(TIMBER_MODEL_PATH)

# 1. TRANSLATION STEP (Timber -> Intermediate Model)
print("Translating timber model to agnostic structural model...")
from ct_dlubal.translator import TimberToStructural

translator = TimberToStructural(connector_mode="rigid", material_name="C24")
structural_model = translator.translate(timber_model)

print(f"  -> Generated {len(structural_model.nodes)} structural nodes.")
print(f"  -> Generated {len(structural_model.members)} structural members.")

# 2. PUSH STEP (Intermediate Model -> Dlubal)
print("Initiating Live push to Dlubal...")
from ct_dlubal.importer import DlubalImporter

try:
    importer = DlubalImporter(app_type=APP_TYPE, delete_all=True, api_key=MY_API_KEY)
    importer.run(structural_model, model_name="test-model")
    print("Successfully exported to Dlubal!")

except Exception as e:
    print(f"Live export failed: {e}")

# 3. (OPTIONAL) SAVE STEP
# from ct_dlubal.exporter import export_file
# export_file(structural_model, r"C:\path\to\output.saf", format="SAF")

