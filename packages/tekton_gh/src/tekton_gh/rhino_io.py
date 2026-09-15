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

    The ramp itself lives in :mod:`tekton_gh.visualize` (pure, tested); this
    is the System.Drawing wrapper for the canvas.

    Returns
    -------
    System.Drawing.Color
    """
    from System.Drawing import Color

    from tekton_gh.visualize import colour_rgb

    return Color.FromArgb(*colour_rgb(value, low, high))



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
    """Report the allowed values for an input.

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
        "  (set 'menu' to True once to get a drop-down)",
    ]


def build_value_list(ghenv, names, param_index=0, nickname="Options"):
    """Create a drop-down for an input - on an explicit button press only.

    A component must never build this by itself. Adding objects during a solve
    crashes Rhino, and deferring through ``ScheduleSolution`` does not save it
    either: the callback is a Python closure that has to survive across the
    .NET delegate boundary, and if it is collected before Grasshopper calls it,
    the process dies with no error at all. Two crashes on 2026-09-10 and
    2026-09-11 came from exactly that.

    Behind a button the situation is different. The user presses it, the
    document is between solves, and the object is created straight away
    instead of from a callback that has to survive anything. Same convenience,
    without the mechanism that did the damage.

    Returns
    -------
    tuple
        ``(created, message)`` - `created` is False when nothing was done
        (already wired, or no document), and `message` says why.
    """
    import Grasshopper
    import System

    component = ghenv.Component
    try:
        param = component.Params.Input[param_index]
    except (IndexError, AttributeError):
        return False, "input {} does not exist".format(param_index)

    if param.SourceCount:
        return False, "'{}' already has a source - leaving it alone".format(param.NickName)

    document = component.OnPingDocument()
    if document is None:
        return False, "no active document"

    value_list = Grasshopper.Kernel.Special.GH_ValueList()
    value_list.CreateAttributes()
    value_list.Name = nickname
    value_list.NickName = nickname
    value_list.ListItems.Clear()
    for name in names:
        value_list.ListItems.Add(
            Grasshopper.Kernel.Special.GH_ValueListItem(name, '"{}"'.format(name))
        )
    value_list.SelectItem(0)

    pivot = component.Attributes.Pivot
    bounds = value_list.Attributes.Bounds
    value_list.Attributes.Pivot = System.Drawing.PointF(
        float(pivot.X - bounds.Width - 90),
        float(pivot.Y - 10 + param_index * 20),
    )

    document.AddObject(value_list, False)
    param.AddSource(value_list)
    return True, "drop-down created with {} entries - set 'menu' back to False".format(len(names))
