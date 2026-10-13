"""Tekton Area Load - a pressure on a beam grid, in kN/m2.

For roofs and floors framed with beams and no plates: the fields between the
horizontal members of one level take the pressure, and TektonApplyLoads hands
each field's load to the members around it (45-degree rule for rectangles,
centroid rule otherwise). That has to happen after translating, because only
then do the members exist that frame each field - so this component only
describes the load, like Point and Member Load.

The regions are closed curves, tested in plan: a field is loaded when its
centre lies inside them by the even-odd rule. Outline plus inner curve is the
ring between them - a canopy around a middle field, say. Where the curves
come from is up to the definition: drawn in Rhino, or built in Grasshopper.
Without regions the whole level is loaded. On plates use Surface Load.
"""
# venv: tekton-test
# r: compas, compas_timber

ghenv.Component.Message = "Area Load"  # type: ignore # noqa: F821


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )


def _polygon(curve):
    """A closed curve as its corner points (document units)."""
    ok, polyline = curve.TryGetPolyline()
    if ok:
        points = list(polyline)
    else:
        # A smooth curve: fine enough to decide which field centres lie inside.
        parameters = curve.DivideByCount(128, True)
        points = [curve.PointAt(t) for t in parameters] if parameters else []
    if len(points) > 1 and points[0].DistanceTo(points[-1]) < 1e-9:
        points = points[:-1]
    return [[p.X, p.Y, p.Z] for p in points]


class _Load(object):
    """Carries the load description to TektonApplyLoads.

    A bare dict does not survive the trip: Grasshopper unpacks it into its
    keys, and a dict inside a list arrives as a .NET Dictionary. A plain
    object goes through untouched - TektonApplyLoads reads `.spec`.
    """

    def __init__(self, spec):
        self.spec = spec

    def __repr__(self):
        return "Tekton {} load, LC {}".format(self.spec.get("kind"), self.spec.get("load_case_id"))


# --------------------- INPUTS ---------------------
regions = regions  # type: ignore # noqa: F821
pressure = pressure  # type: ignore # noqa: F821
load_case = load_case  # type: ignore # noqa: F821
level: float  # type: ignore

# --------------------- SCRIPT ---------------------

load = None

if pressure is None:
    _warn("pressure is needed - in kN/m2 as a vector, (0, 0, -3) is 3 kN/m2 downward.")
else:
    polygons = []
    for curve in regions or []:
        if curve is None:
            continue
        if not curve.IsClosed:
            _warn("A region curve is not closed and was skipped.")
            continue
        polygon = _polygon(curve)
        if len(polygon) >= 3:
            polygons.append(polygon)

    # Wired but empty is not "the whole level": a referenced curve that went
    # missing from the Rhino document arrives as nothing, and loading the
    # whole roof instead would be wrong without anyone noticing.
    wired = ghenv.Component.Params.Input[0].SourceCount > 0  # type: ignore # noqa: F821
    if wired and not polygons:
        _warn("'regions' is connected but no closed curve arrived (a referenced curve missing "
              "from the Rhino document?) - no load. Disconnect it to load the whole level.")
        pressure = None

if pressure is not None:
    load = {
        "kind": "area",
        "regions": polygons,
        "pressure": [pressure.X, pressure.Y, pressure.Z],
        "load_case_id": getattr(load_case, "id", 1),
        "level": None if level is None else float(level),
        "name": getattr(load_case, "name", None),
    }
    print("Area load {} kN/m2, load case {}, {}".format(
        [round(v, 3) for v in load["pressure"]], load["load_case_id"],
        "{} region curve(s)".format(len(polygons)) if polygons else "the whole level"))
    print("Fields are found and loaded by TektonApplyLoads, after translating.")

# Handed over wrapped - see _Load.
if load is not None:
    load = _Load(load)
