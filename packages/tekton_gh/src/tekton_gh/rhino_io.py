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


def attach_value_list(ghenv, names, param_index=0, nickname="Options"):
    """Hang a drop-down on one of the component's inputs, if nothing is wired.

    The pattern people know from Karamba: place the component, the menu is
    there. Without it the value has to be typed as text - error-prone and with
    no overview of what is allowed.

    **The canvas must not be modified during a solve.** An ``AddObject`` in the
    middle of a solve - especially together with ``ExpireSolution`` - crashes
    Rhino (observed 2026-09-10). The work is therefore deferred via
    ``ScheduleSolution`` into a callback that runs once the current solve has
    finished.

    Only acts on a free input: overwriting existing wiring would be
    presumptuous.

    Parameters
    ----------
    ghenv : the component's ``ghenv``
    names : list of str
        Entries of the drop-down. The selected one arrives as a string.
    param_index : int
        Which input to hang it on.
    nickname : str
        Name of the value list on the canvas.

    Returns
    -------
    bool
        True if a menu was scheduled.
    """
    import Grasshopper
    import System

    component = ghenv.Component
    param = component.Params.Input[param_index]
    if param.SourceCount:
        return False

    document = component.OnPingDocument()
    if document is None:
        return False

    def build(_document):
        # Check again: between scheduling and running, the user may well have
        # wired something up.
        if param.SourceCount:
            return
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
        _document.AddObject(value_list, False)
        param.AddSource(value_list)
        param.ExpireSolution(False)

    document.ScheduleSolution(
        10, Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(build)
    )
    return True
