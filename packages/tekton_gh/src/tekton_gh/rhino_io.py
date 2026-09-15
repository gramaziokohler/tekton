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


#: Delegates handed to ScheduleSolution, kept alive until they have run.
#: Grasshopper holds its own reference, so this is belt and braces - but the
#: cost is nothing and the failure mode (a collected delegate) is a crash.
_PENDING_DELEGATES = {}


def attach_value_list(ghenv, names, param_index=0, nickname="Options"):
    """Hang a drop-down on one of the component's inputs, if nothing is wired.

    The pattern people know from Karamba: place the component, the menu is
    there. Runs once per component instance, deferred out of the solve via
    ``ScheduleSolution``.

    Why this crashed twice before (2026-09-10/11) and why it does not now:
    the canvas must not be touched during a solve, so the work goes into a
    scheduled callback. The old callback assumed the component was still
    there when it ran - but when a component gets *replaced* (rebuilt
    userobject, upgrade tool), the old instance leaves the document while its
    callback is still queued, and touching its ``Attributes`` is a native
    crash with no exception. And any Python exception escaping the delegate
    ends the process just as silently. Hence three guards: schedule only once
    per instance, verify the component is still in the document before doing
    anything, and let nothing escape the callback.

    Returns
    -------
    bool
        True if a menu was scheduled now.
    """
    import Grasshopper
    import System

    component = ghenv.Component
    try:
        param = component.Params.Input[param_index]
    except (IndexError, AttributeError):
        return False
    if param.SourceCount:
        return False

    document = component.OnPingDocument()
    if document is None:
        return False

    key = (str(component.InstanceGuid), param_index)
    if key in _PENDING_DELEGATES:
        return False  # already queued - a second solve must not queue a second menu

    def build(_document):
        try:
            _PENDING_DELEGATES.pop(key, None)
            # The component may have left the document since scheduling
            # (replaced, deleted, undo). Touching it then is a crash, not an
            # error - so this check is the whole point.
            if component.OnPingDocument() is None or not _document.Objects.Contains(component):
                return
            if component.Attributes is None or param.SourceCount:
                return
            # A replaced component solves once before the upgrade tool restores
            # its wires. If a list with this name already sits where we would
            # put ours, it is the previous instance's menu: wire it, do not
            # duplicate it.
            for existing in _document.Objects:
                if isinstance(existing, Grasshopper.Kernel.Special.GH_ValueList) and existing.NickName == nickname:
                    dx = component.Attributes.Pivot.X - existing.Attributes.Pivot.X
                    dy = abs(component.Attributes.Pivot.Y - existing.Attributes.Pivot.Y)
                    if 0 < dx < 400 and dy < 120 and existing.Recipients.Count == 0:
                        param.AddSource(existing)
                        component.ExpireSolution(False)
                        return
            value_list = Grasshopper.Kernel.Special.GH_ValueList()
            value_list.CreateAttributes()
            value_list.Name = nickname
            value_list.NickName = nickname
            value_list.ListItems.Clear()
            for name in names:
                value_list.ListItems.Add(Grasshopper.Kernel.Special.GH_ValueListItem(name, '"{}"'.format(name)))
            value_list.SelectItem(0)

            pivot = component.Attributes.Pivot
            bounds = value_list.Attributes.Bounds
            value_list.Attributes.Pivot = System.Drawing.PointF(
                float(pivot.X - bounds.Width - 90),
                float(pivot.Y - 10 + param_index * 20),
            )
            _document.AddObject(value_list, False)
            param.AddSource(value_list)
            component.ExpireSolution(False)
        except Exception:
            # Never let anything cross the delegate boundary. A menu that
            # fails to appear is a nuisance; an exception here kills Rhino.
            pass

    delegate = Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(build)
    _PENDING_DELEGATES[key] = delegate
    document.ScheduleSolution(10, delegate)
    return True


def value_list_items(ghenv, names, param_index=0):
    """Hint lines naming the allowed values of an input - empty when it is wired."""
    component = ghenv.Component
    try:
        param = component.Params.Input[param_index]
    except (IndexError, AttributeError):
        return []
    if param.SourceCount:
        return []
    return ["{}: {}".format(param.NickName, " | ".join(names))]


def build_value_list(ghenv, names, param_index=0, nickname="Options"):
    """Compatibility shim for component instances built before 2026-09-15.

    Those carried a 'menu' button that called this on demand. The drop-down
    now attaches itself; keep the old name so a saved definition with an old
    instance does not turn red on open.
    """
    scheduled = attach_value_list(ghenv, names, param_index=param_index, nickname=nickname)
    return scheduled, "drop-down {} - this component is outdated, replace it from the ribbon".format(
        "scheduled" if scheduled else "already there or not possible")
