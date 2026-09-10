"""Conversions and display helpers between COMPAS/Tekton and Rhino.

Deliberately thin: `compas_rhino.conversions` already covers most of it. Only
what is Tekton-specific lives here - units from the Rhino document, system
lines from the neutral model, a colour ramp for utilisation values.
"""

#: Rhino unit system -> short name of the Tekton unit contract
#: (``compas_timber_fea.core.units.UNIT_SCALES``).
#: Matters because without this translation a mm model silently turns into
#: 200-metre plates - the bug that prompted the unit contract in the first
#: place.
_RHINO_UNIT_NAMES = {
    "Millimeters": "mm",
    "Centimeters": "cm",
    "Decimeters": "dm",
    "Meters": "m",
}


def document_units(default="m"):
    """Unit of the active Rhino document as a Tekton short name.

    Returns
    -------
    str
        One of 'mm', 'cm', 'dm', 'm'. For inches/feet or outside Rhino, the
        default - Tekton knows no imperial units.
    """
    try:
        import Rhino  # noqa: F401  (only available inside Rhino)

        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return default
        name = str(doc.ModelUnitSystem)
        return _RHINO_UNIT_NAMES.get(name, default)
    except ImportError:
        return default


def point_to_rhino_pt(point):
    """`compas.geometry.Point` -> `Rhino.Geometry.Point3d`."""
    import Rhino.Geometry as rg

    return rg.Point3d(point[0], point[1], point[2])


def line_to_rhino(start, end):
    """Two COMPAS points -> `Rhino.Geometry.Line`."""
    import Rhino.Geometry as rg

    return rg.Line(point_to_rhino_pt(start), point_to_rhino_pt(end))


def member_lines(structural_model, scale=1.0):
    """System lines of all members as Rhino lines.

    Parameters
    ----------
    scale : float
        Factor from the model (metres) into document units. For a mm document
        therefore 1000.

    Returns
    -------
    list of Rhino.Geometry.Line
    """
    import Rhino.Geometry as rg

    nodes = {node.id: node.point for node in structural_model.nodes}
    lines = []
    for member in structural_model.members:
        start = nodes.get(member.node_start)
        end = nodes.get(member.node_end)
        if start is None or end is None:
            continue
        lines.append(
            rg.Line(
                rg.Point3d(start[0] * scale, start[1] * scale, start[2] * scale),
                rg.Point3d(end[0] * scale, end[1] * scale, end[2] * scale),
            )
        )
    return lines


def colour_ramp(value, low=0.0, high=1.0):
    """Value -> colour (green -> yellow -> red), for utilisation/deflection.

    Beyond ``high`` the ramp does not keep interpolating but goes hard red: an
    exceedance should catch the eye, not fade out gently.

    Returns
    -------
    System.Drawing.Color
    """
    from System.Drawing import Color

    if high <= low:
        t = 0.0
    else:
        t = (float(value) - low) / (high - low)

    if t <= 0.0:
        return Color.FromArgb(40, 160, 60)
    if t >= 1.0:
        return Color.FromArgb(200, 30, 30)

    if t < 0.5:
        k = t / 0.5
        r = int(40 + (240 - 40) * k)
        g = int(160 + (200 - 160) * k)
        b = int(60 + (40 - 60) * k)
    else:
        k = (t - 0.5) / 0.5
        r = int(240 + (200 - 240) * k)
        g = int(200 + (30 - 200) * k)
        b = int(40 + (30 - 40) * k)
    return Color.FromArgb(r, g, b)


def warn(ghenv, message):
    """Runtime warning on the component (orange bubble)."""
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )


def error(ghenv, message):
    """Runtime error on the component (red bubble)."""
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message
    )


def value_list_items(ghenv, names, param_index=0):
    """Offer a drop-down for an input - without touching the canvas.

    The obvious implementation (create a GH_ValueList and wire it up from
    inside the component) is not safe here. Adding objects during a solve
    crashes Rhino outright, and deferring the work through
    ``ScheduleSolution`` did not help: the callback is a Python closure that
    has to survive across the .NET delegate boundary, and if it is collected
    before Grasshopper calls it, the process dies with no error at all. Two
    crashes on 2026-09-10 and 2026-09-11 were enough.

    So this does the honest thing instead: it reports the allowed values, and
    the component prints them. To get the Karamba-style menu, right-click the
    input and pick "Manage Value List Collection", or drop a value list next
    to it - one gesture, and nothing can take Rhino down with it.

    Parameters
    ----------
    ghenv : the component's ``ghenv``
    names : list of str
        The allowed values.
    param_index : int
        Which input they belong to.

    Returns
    -------
    list of str
        Lines to print: the input's name and what it accepts. Empty when
        something is already wired, because then the hint is just noise.
    """
    component = ghenv.Component
    try:
        param = component.Params.Input[param_index]
    except (IndexError, AttributeError):
        return []
    if param.SourceCount:
        return []
    return [
        "{}: {}".format(param.NickName, " | ".join(names)),
        "  (right-click the input > Manage Value List Collection for a menu)",
    ]
