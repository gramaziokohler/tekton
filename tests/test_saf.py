import sys
import os

import compas
from compas.data import json_load

from tekton_core.translator import TimberToStructural
from tekton_saf.exporter.saf import SAFExporter

# Configuration
HERE = os.path.dirname(__file__)

TIMBER_MODEL_PATH = os.path.join(HERE, "timber_model_sticks.json")
SAF_OUTPUT_PATH = os.path.join(HERE, "structural_model_export.saf")

# =================================================
# ============= MAIN EXECUTION BLOCK ==============

print(f"Loading timber model from: {TIMBER_MODEL_PATH}")
timber_model = json_load(TIMBER_MODEL_PATH)

if timber_model:
    # 1. TRANSLATION STEP (Timber -> Intermediate Model)
    print("Translating timber model to agnostic structural model...")
    translator = TimberToStructural()
    structural_model = translator.translate(timber_model)
    
    print(f"  -> Generated {len(structural_model.nodes)} structural nodes.")
    print(f"  -> Generated {len(structural_model.members)} structural members.")

    # 2. EXPORT STEP (Intermediate Model -> SAF)
    print(f"Initiating SAF export to: {SAF_OUTPUT_PATH}")
    
    try:
        exporter = SAFExporter(structural_model)
        exporter.export(SAF_OUTPUT_PATH)
        print("Successfully exported to SAF!")
    except Exception as e:
        print(f"SAF export failed: {e}")
else:
    print("Failed to load model.")

