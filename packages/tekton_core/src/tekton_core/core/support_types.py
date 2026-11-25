"""Named support types, and the six stiffnesses each of them stands for.

A support is six numbers - three translations, three rotations - where
``inf`` means held, ``0`` means free, and anything in between is a spring.
That is 64 combinations before springs even start, and `Display` already
draws all of them. What was missing is a way to *author* more than three.

The names here are the ones engineers use and RFEM offers, so a model
carries its intent ("roller_x") rather than only its arithmetic. Anything
the catalogue does not cover is still reachable through the explicit
six-value input on the components - the catalogue is a convenience, never a
restriction.

Convention: z is up. A "roller_x" is therefore free to move along x and held
in y and z - the direction in the name is the one that is *released*, which
is how RFEM labels them too.
"""

INF = float("inf")
FREE = 0.0


def _support(ux, uy, uz, rx, ry, rz, name, note=""):
    return {
        "ux": ux, "uy": uy, "uz": uz, "rx": rx, "ry": ry, "rz": rz,
        "name": name, "note": note,
    }


#: name -> the six stiffnesses plus a readable label.
SUPPORT_TYPES = {
    "pinned": _support(
        INF, INF, INF, FREE, FREE, FREE,
        "Pinned - all translations held, free to rotate"),
    "pinned_rz": _support(
        INF, INF, INF, FREE, FREE, INF,
        "Pinned, rotation about z held - RFEM's 'hinged' (gelenkig)",
        "RFEM's own nodal support preset: the engineer's choice under columns. Holding "
        "the twist keeps a hinged column (torsion kept in its end hinges) from spinning."),
    "fixed": _support(
        INF, INF, INF, INF, INF, INF,
        "Fixed - fully restrained"),
    "roller": _support(
        FREE, FREE, INF, FREE, FREE, FREE,
        "Roller - vertical only",
        "Free in both horizontal directions; the classic 2D roller."),
    "roller_x": _support(
        FREE, INF, INF, FREE, FREE, FREE,
        "Roller, free along x"),
    "roller_y": _support(
        INF, FREE, INF, FREE, FREE, FREE,
        "Roller, free along y"),
    "sliding": _support(
        FREE, FREE, INF, INF, INF, INF,
        "Sliding - rotations held, horizontal translation free",
        "A column foot in a guide: it cannot turn, but it can slide."),
    "hinge_x": _support(
        INF, INF, INF, FREE, INF, INF,
        "Hinged about x - rotation released about x only"),
    "hinge_y": _support(
        INF, INF, INF, INF, FREE, INF,
        "Hinged about y - rotation released about y only"),
    "hinge_z": _support(
        INF, INF, INF, INF, INF, FREE,
        "Hinged about z - torsion released"),
    "vertical_only": _support(
        FREE, FREE, INF, FREE, FREE, FREE,
        "Vertical support only",
        "Same as 'roller'; kept because the name is what people look for."),
    "horizontal_only": _support(
        INF, INF, FREE, FREE, FREE, FREE,
        "Horizontal support only",
        "Holds sideways, carries no vertical load - a lateral brace."),
    "free": _support(
        FREE, FREE, FREE, FREE, FREE, FREE,
        "Free - nothing held",
        "Only useful as a starting point for explicit values."),
}

#: Order for drop-downs: the common three first, then the rest.
SUPPORT_TYPE_ORDER = (
    "pinned", "pinned_rz", "fixed", "roller",
    "roller_x", "roller_y", "sliding",
    "hinge_x", "hinge_y", "hinge_z",
    "vertical_only", "horizontal_only", "free",
)

DOF_ORDER = ("ux", "uy", "uz", "rx", "ry", "rz")


def support_type_names():
    """Drop-down entries: ``"roller_x - Roller, free along x"``."""
    return ["{} - {}".format(key, SUPPORT_TYPES[key]["name"]) for key in SUPPORT_TYPE_ORDER]


def key_from_name(entry):
    """The key from a drop-down entry, or the entry itself if it is one."""
    return str(entry or "").split(" - ")[0].strip().lower()


def stiffnesses(support_type, explicit=None, springs=None):
    """The six stiffnesses for a support.

    Parameters
    ----------
    support_type : str
        A catalogue key, or a drop-down entry.
    explicit : sequence, optional
        Six values in the order ux, uy, uz, rx, ry, rz, overriding the type
        entirely. ``"inf"``/``"rigid"``/``"fixed"`` and ``"free"`` are
        accepted as words so a panel can carry them; a number is a spring
        stiffness in kN/m or kNm/rad.
    springs : dict, optional
        Per-DOF override on top of the type, e.g. ``{"uz": 50000}`` for a
        bedded foot. Applied after `explicit`.

    Returns
    -------
    dict
        ``{"ux": ..., ..., "rz": ...}``

    Raises
    ------
    ValueError
        On an unknown type, or six values that are not six. Loudly: a
        support silently falling back to "pinned" changes the structure.
    """
    if explicit is not None:
        values = list(explicit)
        if len(values) != 6:
            raise ValueError(
                "Explicit support values need exactly 6 entries (ux, uy, uz, rx, ry, rz), got {}.".format(
                    len(values)))
        out = {dof: _as_stiffness(value) for dof, value in zip(DOF_ORDER, values)}
    else:
        key = key_from_name(support_type) if support_type else "pinned"
        entry = SUPPORT_TYPES.get(key)
        if entry is None:
            raise ValueError(
                "Unknown support type {!r}. Available: {}.".format(
                    key, ", ".join(SUPPORT_TYPE_ORDER)))
        out = {dof: entry[dof] for dof in DOF_ORDER}

    for dof, value in (springs or {}).items():
        if dof not in DOF_ORDER:
            raise ValueError("Unknown degree of freedom {!r}; expected one of {}.".format(dof, DOF_ORDER))
        out[dof] = _as_stiffness(value)
    return out


def _as_stiffness(value):
    """A number, or one of the words a panel might carry."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("inf", "infinity", "rigid", "fixed", "held"):
            return INF
        if text in ("free", "0", "none", ""):
            return FREE
        try:
            return float(text)
        except ValueError:
            raise ValueError(
                "Cannot read {!r} as a stiffness. Use a number, 'rigid' or 'free'.".format(value))
    return float(value)


def describe(values):
    """One readable line for a set of stiffnesses."""
    parts = []
    for dof in DOF_ORDER:
        value = values[dof]
        if value == INF:
            parts.append("{} held".format(dof))
        elif value == FREE:
            parts.append("{} free".format(dof))
        else:
            parts.append("{} {:g}".format(dof, value))
    return ", ".join(parts)


def matching_type(values, tolerance=1e-9):
    """The catalogue name for these stiffnesses, or None.

    Lets a reader label a support that came back from a backend as six
    numbers, instead of showing the numbers raw.
    """
    for key in SUPPORT_TYPE_ORDER:
        entry = SUPPORT_TYPES[key]
        if all(_same(entry[dof], values[dof], tolerance) for dof in DOF_ORDER):
            return key
    return None


def _same(a, b, tolerance):
    if a == INF or b == INF:
        return a == b
    return abs(a - b) <= tolerance
