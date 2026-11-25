"""The modification factors, and the assumptions they stand on.

.. warning::

   **These tables have not been checked by a structural engineer.** They were
   transcribed from EN 1995-1-1 by a developer reading the standard. A wrong
   value here does not crash and does not look wrong - a k_mod of 0.8 where
   0.6 belongs overstates every resistance in the model by a third, and the
   tests assert against the same transcribed numbers, so they would not catch
   it either. Until an engineer has signed these off, Tekton's design numbers
   are for orientation during design, not for verification. The values are the
   recommended ones from the base Eurocode; CH, DE and AT national annexes
   deviate.

Everything in this module is a *choice*, not a result: service class and
load duration are properties of the building and the action, not of the
geometry, and the neutral model does not carry them (WP1c would add them).
They therefore arrive as explicit inputs with documented defaults, and every
report prints the values it used.

Clause numbers are EN 1995-1-1.
"""

from dataclasses import dataclass
from dataclasses import field

#: Service classes per 2.3.1.3. 1 = heated interior, 2 = covered outdoors,
#: 3 = fully exposed.
SERVICE_CLASSES = (1, 2, 3)

#: Load-duration classes per 2.3.1.2, ordered from longest to shortest.
#: The name is what a report prints, so keep it readable.
LOAD_DURATION_CLASSES = (
    "permanent",
    "long-term",
    "medium-term",
    "short-term",
    "instantaneous",
)

#: Partial factor for a material property, Table 2.3 (recommended values).
GAMMA_M_SOLID = 1.3
GAMMA_M_GLULAM = 1.25

#: Table 3.1 - k_mod for solid timber, glulam and LVL.
#: {service class: {duration class: k_mod}}
_K_MOD = {
    1: {
        "permanent": 0.60,
        "long-term": 0.70,
        "medium-term": 0.80,
        "short-term": 0.90,
        "instantaneous": 1.10,
    },
    2: {
        "permanent": 0.60,
        "long-term": 0.70,
        "medium-term": 0.80,
        "short-term": 0.90,
        "instantaneous": 1.10,
    },
    3: {
        "permanent": 0.50,
        "long-term": 0.55,
        "medium-term": 0.65,
        "short-term": 0.70,
        "instantaneous": 0.90,
    },
}

#: Fallback map, used only when the load catalogue is unavailable. The
#: catalogue (`core/load_catalogue.py`) is the real source: it carries the
#: duration class next to the psi factors for every EN 1990 category, so
#: imposed-storage (long-term) and wind (instantaneous) come out right
#: instead of collapsing into "medium-term".
ACTION_CATEGORY_DURATION = {
    "PERMANENT": "permanent",
    "VARIABLE": "medium-term",
    "SNOW": "short-term",
    "WIND": "short-term",
}

#: k_m for the biaxial bending interaction, 6.1.6(2): 0.7 for rectangular
#: sections of solid timber, glulam and LVL; 1.0 for other cross-sections.
K_M_RECTANGULAR = 0.7
K_M_OTHER = 1.0

#: Reference depth for the size factor, 3.2(3) solid / 3.3(3) glulam, in metres.
_K_H_REF_SOLID = 0.150
_K_H_REF_GLULAM = 0.600
_K_H_MAX_SOLID = 1.3
_K_H_MAX_GLULAM = 1.1


def k_mod(service_class=1, duration="medium-term"):
    """Modification factor for duration and moisture, Table 3.1.

    Parameters
    ----------
    service_class : int
        1, 2 or 3.
    duration : str
        One of :data:`LOAD_DURATION_CLASSES`.

    Raises
    ------
    ValueError
        On an unknown service class or duration - loudly, because a wrong
        k_mod silently scales every check in the model.
    """
    if service_class not in _K_MOD:
        raise ValueError(
            "Unknown service class {!r}; expected one of {}.".format(service_class, SERVICE_CLASSES)
        )
    table = _K_MOD[service_class]
    if duration not in table:
        raise ValueError(
            "Unknown load-duration class {!r}; expected one of {}.".format(duration, LOAD_DURATION_CLASSES)
        )
    return table[duration]


def duration_for_action_category(category):
    """Duration class for an ``action_category`` on a load case.

    Read from the load catalogue, which holds the EN 1990 categories and the
    EN 1995 duration class each of them implies. Falls back to the small map
    above only if the catalogue cannot be imported; unknown categories end up
    at "medium-term", and the caller is expected to report that as a fallback
    rather than a datum.
    """
    try:
        from tekton_core.core.load_catalogue import CATEGORIES
        from tekton_core.core.load_catalogue import category as lookup

        key = str(category or "").strip().upper()
        if key in CATEGORIES:
            return lookup(key).load_duration
    except ImportError:
        pass
    return ACTION_CATEGORY_DURATION.get(str(category).upper(), "medium-term")


def gamma_M_for(material):
    """Partial factor for the given material, Table 2.3.

    Glulam and LVL take 1.25, solid timber 1.3. The distinction is read from
    the material's ``standard`` field, which the presets fill in ("EN 338"
    for solid, "EN 14080" for glulam). An unknown standard gets the
    conservative solid-timber value.
    """
    standard = (getattr(material, "standard", "") or "").upper()
    if "14080" in standard or "GLULAM" in standard or "14374" in standard:
        return GAMMA_M_GLULAM
    return GAMMA_M_SOLID


def k_h_bending(material, height):
    """Size factor for bending strength, 3.2(3) and 3.3(3).

    Small sections are stronger in bending than the characteristic value
    suggests. Below the reference depth the factor raises ``f_mk``; above it
    the factor is 1.0. Returns 1.0 for a non-positive height rather than
    raising: the caller may have an unparsed section, and a missing size
    bonus is the safe direction.
    """
    if not height or height <= 0:
        return 1.0
    standard = (getattr(material, "standard", "") or "").upper()
    if "14080" in standard or "GLULAM" in standard:
        reference, cap, exponent = _K_H_REF_GLULAM, _K_H_MAX_GLULAM, 0.1
    else:
        reference, cap, exponent = _K_H_REF_SOLID, _K_H_MAX_SOLID, 0.2
    if height >= reference:
        return 1.0
    return min(cap, (reference / height) ** exponent)


@dataclass
class DesignAssumptions:
    """Everything the checks assume but cannot read from the model.

    Carried through to the report verbatim: a check whose assumptions are
    invisible is worse than no check, because it looks like a verdict.
    """

    service_class: int = 1
    #: Explicit duration class. When None, it is inferred per load case from
    #: `action_category`, and `inferred_durations` records that.
    load_duration: str = None
    #: Overrides the material-derived value when set.
    gamma_M: float = None
    #: Apply the size factor k_h (3.2(3), 3.3(3)) to the bending strength.
    #: EC5 says "may"; RFEM's timber design leaves it off by default, and
    #: omitting it is the safe side (k_h only ever raises the strength).
    #: Off by default so the ratio matches a certified result as delivered.
    size_factor: bool = False
    #: Which checks were deliberately not run. Printed in every report.
    not_verified: tuple = (
        "buckling (6.3.2)",
        "lateral-torsional buckling (6.3.3)",
    )
    #: Filled during a run: {load_case_id: duration} where it was inferred.
    inferred_durations: dict = field(default_factory=dict)

    def duration_for(self, load_case=None):
        """Duration class to use for this load case."""
        if self.load_duration:
            return self.load_duration
        if load_case is None:
            return "medium-term"
        duration = duration_for_action_category(getattr(load_case, "action_category", ""))
        self.inferred_durations[getattr(load_case, "id", None)] = duration
        return duration

    def k_mod_for(self, load_case=None):
        return k_mod(self.service_class, self.duration_for(load_case))

    def gamma_M_value(self, material):
        return self.gamma_M if self.gamma_M else gamma_M_for(material)

    def describe(self):
        """The assumption block a report prints, as a list of lines."""
        lines = [
            "Service class:      {}".format(self.service_class),
            "Load duration:      {}".format(
                self.load_duration if self.load_duration else "inferred per load case from action category"
            ),
            "gamma_M:            {}".format(
                self.gamma_M if self.gamma_M else "per material (1.3 solid / 1.25 glulam)"
            ),
            "Size factor k_h:    {}".format("applied to f_m" if self.size_factor else "not applied"),
        ]
        if self.inferred_durations:
            inferred = ", ".join(
                "case {}: {}".format(case, duration)
                for case, duration in sorted(self.inferred_durations.items(), key=lambda item: (item[0] is None, item[0]))
            )
            lines.append("Inferred durations: {}".format(inferred))
        if self.not_verified:
            lines.append("NOT verified:       {}".format(", ".join(self.not_verified)))
        return lines
