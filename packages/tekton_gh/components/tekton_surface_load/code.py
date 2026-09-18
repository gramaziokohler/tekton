"""Tekton Surface Load - pressure on plates.

Like Member Load, the mapping goes through the element GUID rather than a
surface number: which surfaces a plate becomes is decided during
idealisation, and the load has to reach all of them.

The load belongs to the plate, not to its mesh. How finely a backend
tessellates is its own business, and a pressure has to survive a change of
mesh density unchanged - which is why this is kN/m2 on a plate and not a set
of nodal forces.

Unit: kN/m2. Negative z is downward, the usual direction for snow and
imposed loads.
"""
# venv: tekton-test
# r: compas, compas_timber

ghenv.Component.Message = "Surface Load"  # type: ignore # noqa: F821


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
plates = plates  # type: ignore # noqa: F821
pressure = pressure  # type: ignore # noqa: F821
load_case = load_case  # type: ignore # noqa: F821
projected = projected  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

load = None

if not plates or pressure is None:
    _warn("plates and pressure are both needed.")
else:
    guids = []
    for plate in plates:
        guid = getattr(plate, "guid", None) or plate
        guids.append(str(guid))

    load = {
        "kind": "surface",
        "element_ids": guids,
        "pressure": [pressure.X, pressure.Y, pressure.Z],
        "load_case_id": getattr(load_case, "id", 1),
        "projected": bool(projected),
    }
    print("Area load {} kN/m2 on {} plate(s), load case {}".format(
        [round(v, 3) for v in load["pressure"]], len(guids), load["load_case_id"]))
    if projected:
        print("  projected: the value is per m2 of plan area, not of sloped surface")
