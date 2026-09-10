"""Tekton Point Load — Einzellast.

Die Last kennt hier nur ihren Angriffspunkt. Die Zuordnung zu einem
Knoten des Statikmodells passiert erst in TektonApplyLoads — vorher
existieren die Knoten noch gar nicht.

Einheiten: Kraft in kN, Moment in kNm (Vertrag des neutralen Modells).
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
    _warn("point und force werden gebraucht.")
else:
    # Bewusst ein leichtes dict statt eines StructuralPointLoad: die Knoten-ID
    # ist erst nach dem Uebersetzen bekannt. TektonApplyLoads macht daraus das
    # echte Lastobjekt.
    load = {
        "kind": "point",
        "position": [point.X, point.Y, point.Z],
        "force": [force.X, force.Y, force.Z],
        "moment": [moment.X, moment.Y, moment.Z] if moment is not None else [0.0, 0.0, 0.0],
        "load_case_id": getattr(load_case, "id", 1),
    }
    print("Einzellast {} kN an ({:.3f}, {:.3f}, {:.3f}), Lastfall {}".format(
        [round(v, 3) for v in load["force"]],
        point.X, point.Y, point.Z, load["load_case_id"]))
