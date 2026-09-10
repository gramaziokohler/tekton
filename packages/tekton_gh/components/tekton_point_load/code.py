"""Tekton Point Load - point load.

Here the load knows only its point of application. Mapping it to a node of the
analysis model happens in TektonApplyLoads - before that the nodes do not even
exist.

Units: force in kN, moment in kNm (the neutral model's contract).
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Point Load"  # type: ignore # noqa: F821


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
point = point  # type: ignore # noqa: F821
force = force  # type: ignore # noqa: F821
moment = moment  # type: ignore # noqa: F821
load_case = load_case  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

load = None

if point is None or force is None:
    _warn("point and force are both needed.")
else:
    # Deliberately a light dict instead of a StructuralPointLoad: the node ID
    # is only known after translating. TektonApplyLoads turns this into the
    # real load object.
    load = {
        "kind": "point",
        "position": [point.X, point.Y, point.Z],
        "force": [force.X, force.Y, force.Z],
        "moment": [moment.X, moment.Y, moment.Z] if moment is not None else [0.0, 0.0, 0.0],
        "load_case_id": getattr(load_case, "id", 1),
    }
    print("Point load {} kN at ({:.3f}, {:.3f}, {:.3f}), load case {}".format(
        [round(v, 3) for v in load["force"]],
        point.X, point.Y, point.Z, load["load_case_id"]))
