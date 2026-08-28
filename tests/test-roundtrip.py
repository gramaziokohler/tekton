"""Live roundtrip: timber model -> RFEM -> calculate -> results back on the beams.

Manual script - needs a running RFEM instance and DLUBAL_API_KEY in .env.
Everything below the gRPC calls is covered by the offline suite in tests/unit;
this script exercises the live half and prints the raw result-table columns so
the parsers' column candidates can be calibrated against a real response.
"""

import os

from compas.data import json_load
from dotenv import load_dotenv

load_dotenv()

MY_API_KEY = os.getenv("DLUBAL_API_KEY")
APP_TYPE = "rfem"  # or "rstab"

HERE = os.path.dirname(__file__)
TIMBER_MODEL_PATH = os.path.join(HERE, "timber_model_sticks.json")

# =================================================
# ============= MAIN EXECUTION BLOCK ==============

print(f"Loading timber model from: {TIMBER_MODEL_PATH}")
timber_model = json_load(TIMBER_MODEL_PATH)

# The committed fixture carries no support_points, so the model would fail
# preflight and RFEM would be asked to solve a mechanism. Mark the lowest
# beam endpoints as supports so the roundtrip has something meaningful to do.
lowest = min(min(b.centerline.start.z, b.centerline.end.z) for b in timber_model.beams)
marked = 0
for beam in timber_model.beams:
    points = [p for p in (beam.centerline.start, beam.centerline.end) if abs(p.z - lowest) < 1e-6]
    if points:
        beam.attributes["support_points"] = [(p.x, p.y, p.z) for p in points]
        marked += 1
print(f"Marked support points on {marked} beams at z={lowest:.3f} (script-side convenience, not a modelling decision)")

# 1. TRANSLATION (timber -> neutral model)
print("Translating timber model to agnostic structural model...")
from compas_timber_fea.translator import TimberToStructural

translator = TimberToStructural(connector_mode="rigid", material_name="C24")
structural_model = translator.translate(timber_model)

print(f"  -> {len(structural_model.nodes)} nodes, {len(structural_model.members)} members, {len(structural_model.supports)} supports")
for entry in translator.report:
    print(f"  -> assumption: {entry}")

# 2. PUSH (neutral model -> Dlubal)
print("Pushing to Dlubal...")
from compas_dlubal.dlubal.importer import DlubalImporter

importer = DlubalImporter(app_type=APP_TYPE, delete_all=True, api_key=MY_API_KEY)
if not importer.run(structural_model, model_name="roundtrip-test-model"):
    raise SystemExit(1)
print("Exported to Dlubal.")

# 3. CALCULATE + READ (Dlubal -> neutral model)
print("Calculating and reading results...")
from compas_dlubal.dlubal.result_reader import DlubalResultReader

result_reader = DlubalResultReader(app_type=APP_TYPE, api_key=MY_API_KEY)
structural_model.results = result_reader.read(load_cases=[1], calculate=True, structural_model=structural_model)

for load_case_id, result_set in structural_model.results.items():
    member_samples = sum(len(values) for values in result_set.member_results.values())
    print(f"  -> LC {load_case_id}: {len(result_set.node_results)} node results, {member_samples} member samples")
    # Raw column names, for calibrating result_parsing's candidates:
    for table, columns in result_set.metadata.get("columns", {}).items():
        print(f"     columns[{table}]: {columns}")
    for table, error in result_set.metadata.get("errors", {}).items():
        print(f"     ERROR[{table}]: {error}")

# 4. ATTACH (neutral results -> timber beams)
print("Attaching results to timber beams...")
from compas_timber_fea.results import ANALYSIS_KEY
from compas_timber_fea.results import attach_results_to_timber

attached = attach_results_to_timber(structural_model, timber_model)
print(f"  -> results attached to {len(attached)} beams")

for beam in list(timber_model.beams)[:3]:
    analysis = beam.attributes.get(ANALYSIS_KEY)
    if analysis:
        for load_case_id, data in analysis["load_cases"].items():
            print(f"  -> beam {str(beam.guid)[:8]} LC{load_case_id} envelope: {data['envelope']}")
