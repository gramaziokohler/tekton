"""The unit contract of the neutral model.

The neutral StructuralModel is metric SI: lengths in metres. Timber models
authored in Rhino/Grasshopper are frequently in millimetres, and nothing in a
COMPAS model states its unit, so a silent factor of 1000 is the default failure
mode: a 200 mm plate becomes a 200 m plate, and the analysis is meaningless
without ever raising an error.

Translation therefore takes the source unit explicitly and converts once, at
the boundary. Everything downstream may assume metres.
"""

#: Scale factor to metres for each supported source unit.
UNIT_SCALES = {
    "m": 1.0,
    "dm": 0.1,
    "cm": 0.01,
    "mm": 0.001,
}

#: A timber cross-section dimension below this (in metres) is implausible and
#: usually means a millimetre model was declared as metres.
IMPLAUSIBLE_SECTION_MIN = 0.005
#: Likewise, a cross-section above this is implausible for timber.
IMPLAUSIBLE_SECTION_MAX = 3.0

#: Plausible range for a timber plate thickness, in metres.
IMPLAUSIBLE_THICKNESS_MIN = 0.003
IMPLAUSIBLE_THICKNESS_MAX = 1.0


class UnitError(ValueError):
    """Raised when a source unit is unknown or the geometry contradicts it."""


def scale_to_meters(units):
    """Return the factor converting ``units`` to metres.

    Raises
    ------
    UnitError
        If the unit is not one of :data:`UNIT_SCALES`.
    """
    try:
        return UNIT_SCALES[units]
    except KeyError:
        supported = ", ".join(sorted(UNIT_SCALES))
        raise UnitError(f"Unknown source unit {units!r}. Supported units: {supported}.") from None


def check_section_plausible(width, height, units="m"):
    """Warn-level sanity check on a converted cross-section.

    Returns a message describing the problem, or None if the section looks
    plausible. Kept as a returned string rather than a raise so a caller can
    collect all findings into one preflight report.
    """
    for label, value in (("width", width), ("height", height)):
        if value <= 0:
            return f"cross-section {label} is {value}, which is not a positive dimension"
        # Reported rounded, so values differing only by float noise produce one
        # message rather than one per member.
        shown = round(value, 4)
        if value < IMPLAUSIBLE_SECTION_MIN:
            return (
                f"cross-section {label} of {shown} m is below {IMPLAUSIBLE_SECTION_MIN} m; "
                f"the model may be authored in a smaller unit than the declared {units!r}"
            )
        if value > IMPLAUSIBLE_SECTION_MAX:
            return (
                f"cross-section {label} of {shown} m exceeds {IMPLAUSIBLE_SECTION_MAX} m; "
                f"the model may be authored in a larger unit than the declared {units!r}"
            )
    return None


def check_thickness_plausible(thickness, units="m"):
    """Sanity check on a converted plate thickness, mirroring the section check."""
    if thickness <= 0:
        return f"plate thickness is {thickness}, which is not a positive dimension"
    # Reported rounded, so values differing only by float noise produce one
    # message rather than one per plate.
    shown = round(thickness, 4)
    if thickness < IMPLAUSIBLE_THICKNESS_MIN:
        return (
            f"plate thickness of {shown} m is below {IMPLAUSIBLE_THICKNESS_MIN} m; "
            f"the model may be authored in a smaller unit than the declared {units!r}"
        )
    if thickness > IMPLAUSIBLE_THICKNESS_MAX:
        return (
            f"plate thickness of {shown} m exceeds {IMPLAUSIBLE_THICKNESS_MAX} m; "
            f"the model may be authored in a larger unit than the declared {units!r}"
        )
    return None
