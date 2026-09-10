"""Tekton Member Load - line load on beams.

The mapping goes through the element GUID, not through member numbers: a
physical beam is split into several members during idealisation (at joints, at
support points), and the load has to go onto all of them.

Unit: kN/m.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Member Load"  # type: ignore # noqa: F821


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
beams = beams  # type: ignore # noqa: F821
force = force  # type: ignore # noqa: F821
load_case = load_case  # type: ignore # noqa: F821
start: float  # type: ignore
end: float  # type: ignore

# --------------------- SCRIPT ---------------------

load = None

if not beams or force is None:
    _warn("beams and force are both needed.")
else:
    guids = []
    for beam in beams:
        guid = getattr(beam, "guid", None) or beam
        guids.append(str(guid))

    load = {
        "kind": "member",
        "element_ids": guids,
        "force": [force.X, force.Y, force.Z],
        "load_case_id": getattr(load_case, "id", 1),
        "dist_start": 0.0 if start is None else float(start),
        "dist_end": 1.0 if end is None else float(end),
    }
    print("Line load {} kN/m on {} element(s), load case {}".format(
        [round(v, 3) for v in load["force"]], len(guids), load["load_case_id"]))
