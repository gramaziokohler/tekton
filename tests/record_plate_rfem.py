"""Record RFEM's answer for the calibration plate (WP0b-Rest).

Pushes ``tests/unit/fixtures/plate_structural.json`` - the simply supported
square plate the OpenSees shell tests measure against Navier - to a running
RFEM with the same 0.35 m mesh target the OpenSees adapter uses, calculates,
and writes every surface sample plus the headline numbers to
``tests/unit/fixtures/plate_rfem_calibration.json``. Needs RFEM and an API
key (``.env``); the tests that read the fixture need neither.

    python tests/record_plate_rfem.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from tekton_core.core.model import StructuralModel  # noqa: E402
from tekton_dlubal.dlubal.importer import DlubalImporter  # noqa: E402
from tekton_dlubal.dlubal.result_reader import DlubalResultReader  # noqa: E402
from tekton_app.worker import read_api_key  # noqa: E402

MESH_SIZE = 0.35
#: RFEM's default gravitational acceleration; the neutral adapters use 9.81.
RFEM_GRAVITY = 10.0


def main():
    fixture_dir = os.path.join(HERE, "unit", "fixtures")
    model = StructuralModel.from_json(os.path.join(fixture_dir, "plate_structural.json"))
    key = read_api_key()

    DlubalImporter(api_key=key, delete_all=True, mesh_size=MESH_SIZE).run(model)
    results = DlubalResultReader(api_key=key).read(load_cases=[1], calculate=True, structural_model=model)
    result_set = results[1]

    samples = result_set.surface_results[1]
    worst = max(samples, key=lambda s: abs(s.displacement.z))
    reactions = sum(node.reaction_force.z for node in result_set.node_results.values() if node.reaction_force)

    record = {
        "note": (
            "RFEM 6.13 for tests/unit/fixtures/plate_structural.json: simply supported square plate "
            "4 x 4 m, t = 0.2 m, C24 pushed as an isotropic plate (E0_mean, nu = 0, G = E/2), "
            "self-weight, mesh target {} m, nodal supports on the 44 outline nodes. Neutral units "
            "(m, kN, kNm/m, kN/m), Z up. Recorded {}."
        ).format(MESH_SIZE, __import__("time").strftime("%Y-%m-%d")),
        "gravity": RFEM_GRAVITY,
        "mesh_size": MESH_SIZE,
        "surface_columns": result_set.metadata["columns"].get("surface_forces"),
        "max_displacement": {
            "uz": worst.displacement.z,
            "position": [worst.position.x, worst.position.y, worst.position.z],
            "m_x": worst.moment_x, "m_y": worst.moment_y, "m_xy": worst.moment_xy,
        },
        "reaction_sum_z": reactions,
        "samples": [
            {
                "x": s.position.x, "y": s.position.y,
                "uz": s.displacement.z if s.displacement else None,
                "n_x": s.membrane_force_x, "n_y": s.membrane_force_y, "n_xy": s.membrane_force_xy,
                "m_x": s.moment_x, "m_y": s.moment_y, "m_xy": s.moment_xy,
                "v_x": s.metadata.get("v_x"), "v_y": s.metadata.get("v_y"),
            }
            for s in samples
        ],
    }
    target = os.path.join(fixture_dir, "plate_rfem_calibration.json")
    with open(target, "w") as handle:
        json.dump(record, handle, indent=1)
    print("{} samples, max uz {:.4e} at ({:.3f}, {:.3f}), sum Rz {:.3f} -> {}".format(
        len(samples), worst.displacement.z, worst.position.x, worst.position.y, reactions, target))


if __name__ == "__main__":
    main()
