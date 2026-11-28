"""EN 1990 action categories, their factors, and the combinations they generate.

.. warning::

   **These tables have not been checked by a structural engineer.** The psi
   factors and partial factors were transcribed from EN 1990 by a developer
   reading the standard. A wrong psi_0 produces combinations that look
   entirely ordinary and are wrong throughout; the tests assert against the
   same transcribed numbers and would not catch it. The values are the
   recommended ones from the base Eurocode - national annexes deviate. Until
   an engineer has reviewed them, use the generated combinations for
   orientation, not for verification.

Utilisation for self-weight alone is not a design value. What turns load
cases into one is the combination rule of EN 1990 6.4.3: every variable
action takes a turn as the leading one, the others enter reduced by psi_0,
and the worst result governs.

The catalogue carries only what the *code* fixes - the psi factors of
Table A1.1 and the partial factors of Table A1.2(B). The load values
themselves stay the user's: a snow load depends on the site, and no
catalogue can know it. Categories A-H for imposed loads, plus snow, wind
and thermal, are what EN 1991 distinguishes and what the psi factors are
tabulated against.

National annexes differ. The values here are the recommended ones; where a
country deviates, that belongs in an override rather than a silent edit of
this table. The same argument applies to gamma_M.
"""

from dataclasses import dataclass
from dataclasses import field

#: Permanent actions: unfavourable and favourable partial factor,
#: EN 1990 Table A1.2(B).
GAMMA_G_UNFAVOURABLE = 1.35
GAMMA_G_FAVOURABLE = 1.00

#: Variable actions, same table.
GAMMA_Q_UNFAVOURABLE = 1.50
GAMMA_Q_FAVOURABLE = 0.00

#: Reduction factor for permanent actions in the "6.10b" expression.
XI_REDUCTION = 0.85


@dataclass(frozen=True)
class ActionCategory:
    """One action category with the factors EN 1990 assigns to it.

    ``psi_0`` combines, ``psi_1`` is the frequent value, ``psi_2`` the
    quasi-permanent one. ``permanent`` marks the self-weight family, which
    is never "leading" and takes gamma_G rather than gamma_Q.
    """

    key: str
    name: str
    psi_0: float = 0.0
    psi_1: float = 0.0
    psi_2: float = 0.0
    permanent: bool = False
    #: What EN 1995 calls this for k_mod (Table 3.1). Needed by the design
    #: checks, which otherwise have to guess from the category name.
    load_duration: str = "medium-term"
    note: str = ""

    @property
    def gamma_unfavourable(self):
        return GAMMA_G_UNFAVOURABLE if self.permanent else GAMMA_Q_UNFAVOURABLE

    @property
    def gamma_favourable(self):
        return GAMMA_G_FAVOURABLE if self.permanent else GAMMA_Q_FAVOURABLE


#: EN 1990 Table A1.1 (recommended values) plus the EN 1995 duration class.
CATEGORIES = {
    "PERMANENT": ActionCategory(
        "PERMANENT", "Permanent (self-weight, finishes)",
        psi_0=1.0, psi_1=1.0, psi_2=1.0, permanent=True,
        load_duration="permanent",
        note="Never leading; gamma_G applies.",
    ),
    "A": ActionCategory(
        "A", "Imposed - domestic, residential",
        psi_0=0.7, psi_1=0.5, psi_2=0.3, load_duration="medium-term"),
    "B": ActionCategory(
        "B", "Imposed - office",
        psi_0=0.7, psi_1=0.5, psi_2=0.3, load_duration="medium-term"),
    "C": ActionCategory(
        "C", "Imposed - congregation areas",
        psi_0=0.7, psi_1=0.7, psi_2=0.6, load_duration="medium-term"),
    "D": ActionCategory(
        "D", "Imposed - shopping areas",
        psi_0=0.7, psi_1=0.7, psi_2=0.6, load_duration="medium-term"),
    "E": ActionCategory(
        "E", "Imposed - storage",
        psi_0=1.0, psi_1=0.9, psi_2=0.8, load_duration="long-term",
        note="Storage counts as long-term for k_mod."),
    "F": ActionCategory(
        "F", "Traffic - vehicle weight <= 30 kN",
        psi_0=0.7, psi_1=0.7, psi_2=0.6, load_duration="short-term"),
    "G": ActionCategory(
        "G", "Traffic - vehicle weight 30-160 kN",
        psi_0=0.7, psi_1=0.5, psi_2=0.3, load_duration="short-term"),
    "H": ActionCategory(
        "H", "Roofs (not accessible except for maintenance)",
        psi_0=0.0, psi_1=0.0, psi_2=0.0, load_duration="short-term"),
    "SNOW": ActionCategory(
        "SNOW", "Snow - sites up to 1000 m a.s.l.",
        psi_0=0.5, psi_1=0.2, psi_2=0.0, load_duration="short-term",
        note="Above 1000 m: psi_0 0.7, psi_1 0.5, psi_2 0.2 (CH/FIN/IS/N/S)."),
    "SNOW_HIGH": ActionCategory(
        "SNOW_HIGH", "Snow - sites above 1000 m a.s.l.",
        psi_0=0.7, psi_1=0.5, psi_2=0.2, load_duration="medium-term"),
    "WIND": ActionCategory(
        "WIND", "Wind",
        psi_0=0.6, psi_1=0.2, psi_2=0.0, load_duration="instantaneous"),
    "THERMAL": ActionCategory(
        "THERMAL", "Temperature (non-fire)",
        psi_0=0.6, psi_1=0.5, psi_2=0.0, load_duration="short-term"),
    # Kept so models written before the catalogue still load. "VARIABLE" says
    # nothing about which psi applies, so it borrows category A and says so.
    "VARIABLE": ActionCategory(
        "VARIABLE", "Variable (unspecified)",
        psi_0=0.7, psi_1=0.5, psi_2=0.3, load_duration="medium-term",
        note="Unspecified - factors borrowed from category A. Pick a real category."),
}

#: Order the drop-downs and reports use: permanent first, then imposed A-H,
#: then the climatic actions.
CATEGORY_ORDER = (
    "PERMANENT",
    "A", "B", "C", "D", "E", "F", "G", "H",
    "SNOW", "SNOW_HIGH", "WIND", "THERMAL",
    "VARIABLE",
)


def category(key, default="VARIABLE"):
    """Look up a category, tolerating case and unknown names.

    An unknown key falls back rather than raising: a model from elsewhere
    should still analyse, and the fallback's ``note`` says the factors were
    borrowed.
    """
    if isinstance(key, ActionCategory):
        return key
    found = CATEGORIES.get(str(key or "").strip().upper())
    return found if found is not None else CATEGORIES[default]


def category_names():
    """Drop-down entries: ``"A - Imposed - office"`` and the like."""
    return ["{} - {}".format(key, CATEGORIES[key].name) for key in CATEGORY_ORDER]


def key_from_name(entry):
    """The key from a drop-down entry, or the entry itself if it is one."""
    return str(entry or "").split(" - ")[0].strip().upper()


@dataclass
class GeneratedCombination:
    """One combination, with enough provenance to be checked by hand."""

    name: str
    combination_type: str            # "ULS" | "SLS_CHARACTERISTIC" | ...
    factors: dict = field(default_factory=dict)   # load case id -> factor
    leading_case: int = None
    expression: str = ""             # "EN 1990 6.10", for the report
    description: str = ""


def _variable_cases(load_cases):
    return [case for case in load_cases if not category(getattr(case, "action_category", "")).permanent]


def _permanent_cases(load_cases):
    return [case for case in load_cases if category(getattr(case, "action_category", "")).permanent]


def generate_combinations(load_cases, include_sls=True, favourable_permanent=False):
    """Generate the EN 1990 combinations for these load cases.

    ULS per 6.10: every variable action leads once, the rest enter with
    psi_0. With no variable action at all, the permanent-only combination is
    still produced - that is a design situation, not an empty result.

    SLS per 6.14b (characteristic) and 6.16b (quasi-permanent), because
    deflection limits are checked against those, not against ULS.

    Parameters
    ----------
    load_cases : list of StructuralLoadCase
    include_sls : bool
        Also generate the serviceability combinations.
    favourable_permanent : bool
        Use gamma_G = 1.0 for the permanent actions. Relevant for uplift,
        where self-weight helps and must not be inflated.

    Returns
    -------
    list of GeneratedCombination
    """
    permanent = _permanent_cases(load_cases)
    variable = _variable_cases(load_cases)
    gamma_g = GAMMA_G_FAVOURABLE if favourable_permanent else GAMMA_G_UNFAVOURABLE

    out = []

    if not variable:
        if permanent:
            out.append(GeneratedCombination(
                name="ULS - permanent only",
                combination_type="ULS",
                factors={case.id: gamma_g for case in permanent},
                expression="EN 1990 6.10",
                description="No variable action in the model.",
            ))
    else:
        for leading in variable:
            factors = {case.id: gamma_g for case in permanent}
            factors[leading.id] = GAMMA_Q_UNFAVOURABLE
            for other in variable:
                if other.id == leading.id:
                    continue
                psi_0 = category(other.action_category).psi_0
                if psi_0:
                    factors[other.id] = GAMMA_Q_UNFAVOURABLE * psi_0
            out.append(GeneratedCombination(
                name="ULS - {} leading".format(leading.name or "case {}".format(leading.id)),
                combination_type="ULS",
                factors=factors,
                leading_case=leading.id,
                expression="EN 1990 6.10",
                description="gamma_G {:.2f}, gamma_Q {:.2f}, others by psi_0.".format(
                    gamma_g, GAMMA_Q_UNFAVOURABLE),
            ))

    if not include_sls:
        return out

    if permanent or variable:
        for leading in (variable or [None]):
            factors = {case.id: 1.0 for case in permanent}
            if leading is not None:
                factors[leading.id] = 1.0
                for other in variable:
                    if other.id == leading.id:
                        continue
                    psi_0 = category(other.action_category).psi_0
                    if psi_0:
                        factors[other.id] = psi_0
            out.append(GeneratedCombination(
                name="SLS characteristic{}".format(
                    "" if leading is None else " - {} leading".format(
                        leading.name or "case {}".format(leading.id))),
                combination_type="SLS_CHARACTERISTIC",
                factors=factors,
                leading_case=None if leading is None else leading.id,
                expression="EN 1990 6.14b",
                description="Unfactored; for deflection limits.",
            ))

        quasi = {case.id: 1.0 for case in permanent}
        for case in variable:
            psi_2 = category(case.action_category).psi_2
            if psi_2:
                quasi[case.id] = psi_2
        out.append(GeneratedCombination(
            name="SLS quasi-permanent",
            combination_type="SLS_QUASI_PERMANENT",
            factors=quasi,
            expression="EN 1990 6.16b",
            description="psi_2 values; the basis for creep (k_def).",
        ))

    return out


def to_load_combinations(generated, start_id=1):
    """Turn generated combinations into :class:`LoadCombination` objects."""
    from tekton_core.core.releases import LoadCombination

    out = []
    for offset, item in enumerate(generated):
        out.append(LoadCombination(
            id=start_id + offset,
            name=item.name,
            factors=dict(item.factors),
            combination_type=item.combination_type,
        ))
    return out


def describe(generated):
    """The combinations as readable lines, for a report or a component."""
    lines = []
    for item in generated:
        terms = ", ".join(
            "{}x LC{}".format(_trim(factor), case_id)
            for case_id, factor in sorted(item.factors.items())
        )
        lines.append("{} [{}]: {}".format(item.name, item.expression, terms or "no cases"))
    return lines


def _trim(value):
    text = "{:.3f}".format(float(value)).rstrip("0").rstrip(".")
    return text or "0"
