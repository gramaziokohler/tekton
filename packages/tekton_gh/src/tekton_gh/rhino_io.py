"""Konvertierungen und Anzeige-Helfer zwischen COMPAS/Tekton und Rhino.

Bewusst dünn: `compas_rhino.conversions` kann das meiste schon. Hier steht nur,
was Tekton-spezifisch ist — Einheiten aus dem Rhino-Dokument, Systemlinien aus
dem neutralen Modell, eine Farbrampe für Ausnutzungsgrade.
"""

#: Rhino-Einheitensystem -> Kürzel des Tekton-Einheiten-Vertrags
#: (``compas_timber_fea.core.units.UNIT_SCALES``).
#: Wichtig, weil ein mm-Modell ohne diese Übersetzung stumm zu 200-Meter-Platten
#: wird — der Bug, der den Einheiten-Vertrag überhaupt ausgelöst hat.
_RHINO_UNIT_NAMES = {
    "Millimeters": "mm",
    "Centimeters": "cm",
    "Decimeters": "dm",
    "Meters": "m",
}


def document_units(default="m"):
    """Einheit des aktiven Rhino-Dokuments als Tekton-Kürzel.

    Returns
    -------
    str
        Eines von 'mm', 'cm', 'dm', 'm'. Bei Zoll/Fuß oder außerhalb von Rhino
        der Default — Tekton kennt keine imperialen Einheiten.
    """
    try:
        import Rhino  # noqa: F401  (nur in Rhino verfügbar)

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
    """Zwei COMPAS-Punkte -> `Rhino.Geometry.Line`."""
    import Rhino.Geometry as rg

    return rg.Line(point_to_rhino_pt(start), point_to_rhino_pt(end))


def member_lines(structural_model, scale=1.0):
    """Systemlinien aller Stäbe als Rhino-Linien.

    Parameters
    ----------
    scale : float
        Faktor vom Modell (Meter) in Dokumenteinheiten. Bei einem
        mm-Dokument also 1000.

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
    """Wert -> Farbe (grün -> gelb -> rot), für Ausnutzung/Verformung.

    Über ``high`` hinaus wird nicht weiter interpoliert, sondern hart rot:
    eine Überschreitung soll ins Auge springen, nicht sanft ausbleichen.

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
    """Laufzeit-Warnung an der Komponente (orange Blase)."""
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )


def error(ghenv, message):
    """Laufzeit-Fehler an der Komponente (rote Blase)."""
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message
    )
