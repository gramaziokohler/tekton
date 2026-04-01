"""Python COMPAS template"""
# venv: ct_dlubal-dev

# import local packages (dev mode)
import sys
import os

CT_SRC = r"C:\path\to\compas_timber\src"
TD_SRC = r"C:\path\to\timber_design\src"
DL_SRC = r"C:\path\to\ct_dlubal\src"

for p in [TD_SRC, CT_SRC, DL_SRC]:
    if p not in sys.path:
        sys.path.insert(0, p)

# force python to forget any previously loaded dlubal or ct_dlubal modules 
# so grasshopper reliably pulls the newest version of your code every compute
for mod_name in list(sys.modules.keys()):
    if mod_name.startswith("ct_dlubal") or mod_name.startswith("dlubal"):
        del sys.modules[mod_name]

import compas
import compas_timber

# grasshopper reload
from compas_rhino.devtools import DevTools
DevTools.ensure_path()


# setup dlubal
MY_API_KEY = "ak-REDACTED-ROTATED-2026-09"
APP_TYPE = "rfem"
RUN_EXPORT = True  # send to rstab/rfem

# outputs for gh
structural_geometry = []
connector_geometry = []

TOL = 0.3 # abstand ab dem knoten generiert werden

if timber_model:
    # 1. beams verbinden (tolerance definieren)
    print(f"verbinde beams mit max_distance {TOL}...")
    timber_model.connect_adjacent_beams(max_distance=TOL)
    
    # balken aufteilen für dlubal (strukturelle segmente)
    print("segmentiere balken...")
    timber_model.create_beam_structural_segments()
    
    # 2. geometrie rausziehen für grasshopper preview
    for beam in timber_model.beams:
        for segment in timber_model.get_beam_structural_segments(beam):
            structural_geometry.append(segment.segment)

    # connectors rausziehen
    for joint in timber_model.joints:
        # get both beams of joint to define connector
        if len(joint.elements) == 2:
            beam_a, beam_b = joint.elements
            try:
                for segment in timber_model.get_structural_connector_segments(beam_a, beam_b):
                    connector_geometry.append(segment.segment)
            except Exception:
                pass
        
    # 3. übersetzen (Timber -> Structural) 
    print("Translating timber model to agnostic structural model...")
    from ct_dlubal.translator import TimberToStructural
    translator = TimberToStructural(connector_mode="rigid", material_name="C24")
    structural_model = translator.translate(timber_model)

    # 4. export starten
    if RUN_EXPORT:
        print("starte export zu dlubal...")
        from ct_dlubal.dlubal.importer import DlubalImporter
        importer = DlubalImporter(app_type=APP_TYPE, delete_all=True, api_key=MY_API_KEY, load_cases=["sw", "snow"])
        importer.run(structural_model, model_name=model_name or "GH Timber Export")
        print("export fertig!")
    else:
        print("export pausiert (RUN_EXPORT = False)")
else:
    print("warte auf model...")
