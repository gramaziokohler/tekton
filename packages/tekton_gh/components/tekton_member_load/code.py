"""Tekton Member Load — Streckenlast auf Balken.

Die Zuordnung laeuft ueber die Bauteil-GUID, nicht ueber Stabnummern:
ein physischer Balken wird beim Idealisieren in mehrere Staebe geteilt
(an Anschluessen, an Auflagerpunkten), und die Last muss auf alle davon.

Einheit: kN/m.
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
    _warn("beams und force werden gebraucht.")
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
    print("Streckenlast {} kN/m auf {} Bauteil(e), Lastfall {}".format(
        [round(v, 3) for v in load["force"]], len(guids), load["load_case_id"]))
