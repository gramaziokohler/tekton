import os
import sys

# Paths setup
CT_SRC = r"C:\path\to\compas_timber\src"
DL_SRC = r"C:\path\to\ct_dlubal\src"

for p in [CT_SRC, DL_SRC]:
    if p not in sys.path:
        sys.path.insert(0, p)

from compas.data import json_load
from ct_dlubal.translator import TimberToStructural
from ct_dlubal.exporter import StructuralExporter

# 1. Load Model
model_path = r"C:\path\to\ct_dlubal\tests\timber-models\timber_model-rotated-beams-3.json"
print(f"Loading timber model: {model_path}")
timber_model = json_load(model_path)

if timber_model:
    # 2. Translate to neutral StructuralModel
    print("Translating to neutral StructuralModel...")
    translator = TimberToStructural()
    structural_model = translator.translate(timber_model)
    
    print(f"Nodes: {len(structural_model.nodes)}")
    print(f"Members: {len(structural_model.members)}")

    # 3. Export to SAF
    saf_path = r"C:\path\to\ct_dlubal\tests\structural_model_export.saf"
    print(f"Initiating SAF export to: {saf_path}")
    
    exporter = StructuralExporter(structural_model)
    exporter.to_saf(saf_path)
else:
    print("Failed to load model.")
