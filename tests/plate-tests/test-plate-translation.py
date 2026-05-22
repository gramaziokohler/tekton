import sys
import os

from compas.data import json_load
from compas_timber_fea.translator import TimberToStructural

HERE = os.path.dirname(__file__)
# Path to the plates model
TIMBER_MODEL_PATH = os.path.abspath(os.path.join(HERE, "..", "timber_model_plates.json"))

def main():
    print(f"Loading timber model from: {TIMBER_MODEL_PATH}")
    timber_model = json_load(TIMBER_MODEL_PATH)

    print("Translating plates timber model to agnostic structural model...")
    translator = TimberToStructural(connector_mode="rigid", material_name="C24")
    structural_model = translator.translate(timber_model)

    print("\n--- Translation Summary ---")
    print(f"Nodes: {len(structural_model.nodes)}")
    print(f"Members: {len(structural_model.members)}")
    print(f"Surfaces: {len(structural_model.surfaces)}")
    print(f"Surface Connections: {len(structural_model.surface_connections)}")
    
    print("\nSurfaces:")
    for s in structural_model.surfaces:
        print(f"  Surface(ID={s.id}, Nodes={s.nodes}, ThicknessID={s.thickness_id})")
        
    print("\nSurface Connections:")
    for c in structural_model.surface_connections:
        print(f"  Connection(ID={c.id}, Nodes={c.nodes})")

if __name__ == "__main__":
    main()
