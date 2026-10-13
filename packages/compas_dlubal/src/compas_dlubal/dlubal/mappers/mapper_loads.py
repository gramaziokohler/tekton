"""Load cases, loads and combinations, mapped from the neutral model.

Loads are authored in the neutral StructuralModel so that every backend applies
the same loading. This mapper translates that model, rather than defining a
catalogue of its own.
"""

from google.protobuf import symbol_database

from compas_dlubal.dlubal.conventions import force_to_dlubal
from compas_dlubal.dlubal.conventions import vector_to_dlubal


def _message_class(descriptor):
    """Resolve a nested protobuf message class from its descriptor.

    Nested row types are not exposed as attributes of their container, so they
    are looked up by their fully qualified name instead.
    """
    return symbol_database.Default().GetSymbol(descriptor.full_name)


#: Neutral action categories -> RFEM action-category enum names.
#: RFEM offers many code-specific variants; these are the plain EN 1990 ones.
#: Neutral action categories -> RFEM action-category enum names.
#:
#: The enum carries every standard RFEM knows; which of its values a load
#: case may actually take depends on the active combination-wizard standard,
#: and an invalid one is refused on create ("Attribute 'action_category' or
#: the attribute on which it depends is invalid"). Every name below was
#: probed live against RFEM 6.13 under EN 1990 (2026-10-13). Three that read
#: plausibly are **not** valid there and are therefore absent: the SIA-style
#: ``SNOW_ACTION_FSN``, the generic ``IMPOSED_ACTION_Q``, and
#: ``ACTIONS_DUE_TO_CLIMATE_CHANGES_..._QC``.
#:
#: A category with no entry here is left unset: RFEM then applies its own
#: default (permanent) and :class:`LoadMapper` records it in
#: ``unmapped_categories`` so the push can say so. Guessing a neighbouring
#: category instead would put a wrong psi into RFEM's own combinations.
ACTION_CATEGORY_NAMES = {
    "PERMANENT": "ACTION_CATEGORY_PERMANENT_G",
    # EN 1990 imposed-load categories A-H (core/load_catalogue.py).
    "A": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_A_DOMESTIC_RESIDENTIAL_AREAS_QI_A",
    "B": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_B_OFFICE_AREAS_QI_B",
    "C": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_C_CONGREGATION_AREAS_QI_C",
    "D": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_D_SHOPPING_AREAS_QI_D",
    "E": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_E_STORAGE_AREAS_QI_E",
    "F": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_F_ROOFS_ACCESSIBLE_ONLY_PRIVATELY_QI_F",
    "G": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_G1_ROOFS_SLOPE_LESS_THAN_20_Q_G1",
    "H": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_H_ROOFS_QI_H",
    "SNOW": "ACTION_CATEGORY_SNOW_ICE_LOADS_H_LESS_OR_EQUAL_TO_1000_M_QS",
    "SNOW_HIGH": "ACTION_CATEGORY_SNOW_ICE_LOADS_H_GREATER_THAN_1000_M_QS",
    "WIND": "ACTION_CATEGORY_WIND_QW",
    "THERMAL": "ACTION_CATEGORY_TEMPERATURE_NON_FIRE_QT",
    # The catalogue's legacy "unspecified variable" borrows category A's psi
    # and says so, so RFEM gets the same category - anything else would make
    # its combinations disagree with ours over the same load case. RFEM has
    # no generic variable action under EN 1990 (IMPOSED_ACTION_Q is refused).
    "VARIABLE": "ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_A_DOMESTIC_RESIDENTIAL_AREAS_QI_A",
}



#: Neutral combination types -> (RFEM design situation number, type enum name, label).
#: RFEM will not solve a load combination without a design situation, and the
#: timber design add-on designs only what sits in a ULS one. One situation
#: per type, numbered so a wizard-made situation (design_setup.py, no. 1)
#: and an authored ULS share the number and therefore the add-on's attention.
DESIGN_SITUATIONS = {
    "ULS": (1, "DESIGN_SITUATION_TYPE_STR_PERMANENT_AND_TRANSIENT_6_10", "ULS persistent/transient (6.10)"),
    "SLS_CHARACTERISTIC": (2, "DESIGN_SITUATION_TYPE_SLS_CHARACTERISTIC", "SLS characteristic (6.14b)"),
    "SLS_QUASI_PERMANENT": (3, "DESIGN_SITUATION_TYPE_SLS_QUASI_PERMANENT", "SLS quasi-permanent (6.16b)"),
}


def design_situation_for(combination_type):
    """(number, enum name, label) for a neutral combination type; unknown types count as ULS."""
    return DESIGN_SITUATIONS.get((combination_type or "ULS").upper(), DESIGN_SITUATIONS["ULS"])


class LoadMapper:
    """Maps neutral load cases, loads and combinations to Dlubal objects."""

    def __init__(self, Loc, Loads=None, numbering=None):
        self.Loc = Loc
        # NodalLoad/MemberLoad live in a different proto module than LoadCase.
        self.Loads = Loads
        self._load_id_counter = 1
        #: Categories RFEM was not given, as (load case id, category). The
        #: importer prints them: silently designing an imposed load as
        #: permanent is the failure an engineer must not be surprised by.
        self.unmapped_categories = []
        # Loads reference members, surfaces and nodes, all of which carry
        # hash ids. Load cases have their own dense counter.
        from compas_dlubal.dlubal.numbering import Numbering

        self.numbering = numbering or Numbering()

    # -- load cases ---------------------------------------------------------

    def map_load_cases(self, load_cases, analysis_settings_no=1):
        """Map neutral load cases, preceded by the static analysis settings they reference."""
        objects = [self.Loc.StaticAnalysisSettings(no=analysis_settings_no, name="Linear Analysis", analysis_type=0)]

        for load_case in load_cases:
            kwargs = dict(
                no=load_case.id,
                name=load_case.name,
                analysis_type=1,
                static_analysis_settings=analysis_settings_no,
            )
            if load_case.self_weight:
                kwargs["self_weight_active"] = True
                # Gravity acts along RFEM's global Z, which points down.
                kwargs["self_weight_factor_z"] = 1.0

            action_category = self._action_category(load_case.action_category, load_case.id)
            if action_category is not None:
                kwargs["action_category"] = action_category

            objects.append(self.Loc.LoadCase(**kwargs))

        return objects

    def _action_category(self, category, load_case_id=None):
        """Resolve a neutral action category to the RFEM enum, or None when there is no valid one."""
        name = ACTION_CATEGORY_NAMES.get((category or "").upper())
        enum_type = self.Loc.LoadCase.DESCRIPTOR.fields_by_name["action_category"].enum_type
        value = enum_type.values_by_name.get(name) if name else None
        if value is None:
            if category:
                self.unmapped_categories.append((load_case_id, str(category)))
            return None
        return value.number

    # -- loads --------------------------------------------------------------

    def map_point_load(self, point_load):
        """Map a nodal force/moment vector to one Dlubal NodalLoad.

        Vectors are authored in the neutral Z-up space and rotated into
        Dlubal's Z-down space here - a downward force (negative z) becomes a
        positive z force in RFEM.
        """
        if self.Loads is None:
            raise AttributeError("LoadMapper needs the loads module to create nodal loads")

        load_type = self._enum(self.Loads.NodalLoad, "load_type", "LOAD_TYPE_COMPONENTS")
        force = vector_to_dlubal(point_load.force)
        moment = vector_to_dlubal(point_load.moment)

        load = self.Loads.NodalLoad(
            no=self._next_id(),
            nodes=[self.numbering.node(point_load.node_id)],
            load_case=point_load.load_case_id,
            load_type=load_type,
            components_force_x=force_to_dlubal(force.x),
            components_force_y=force_to_dlubal(force.y),
            components_force_z=force_to_dlubal(force.z),
            components_moment_x=force_to_dlubal(moment.x),
            components_moment_y=force_to_dlubal(moment.y),
            components_moment_z=force_to_dlubal(moment.z),
        )
        return load

    def map_member_load(self, member_load):
        """Map a uniform member line load.

        The neutral model carries a force vector per unit length; RFEM applies a
        magnitude along one direction, so a vector with several components
        becomes one load object per component.
        """
        if self.Loads is None:
            raise AttributeError("LoadMapper needs the loads module to create member loads")

        load_type = self._enum(self.Loads.MemberLoad, "load_type", "LOAD_TYPE_FORCE")
        distribution = self._enum(self.Loads.MemberLoad, "load_distribution", "LOAD_DISTRIBUTION_UNIFORM")

        force = vector_to_dlubal(member_load.force)
        directions = (
            ("x", force.x, "LOAD_DIRECTION_GLOBAL_X_OR_USER_DEFINED_U_TRUE_LENGTH"),
            ("y", force.y, "LOAD_DIRECTION_GLOBAL_Y_OR_USER_DEFINED_V_TRUE_LENGTH"),
            ("z", force.z, "LOAD_DIRECTION_GLOBAL_Z_OR_USER_DEFINED_W_TRUE_LENGTH"),
        )

        loads = []
        for _axis, magnitude, direction_name in directions:
            if not magnitude:
                continue
            loads.append(
                self.Loads.MemberLoad(
                    no=self._next_id(),
                    members=[self.numbering.member(member_load.member_id)],
                    load_case=member_load.load_case_id,
                    load_type=load_type,
                    load_distribution=distribution,
                    load_direction=self._enum(self.Loads.MemberLoad, "load_direction", direction_name),
                    magnitude=force_to_dlubal(magnitude),
                )
            )
        return loads

    def map_surface_load(self, surface_load):
        """Map a uniform pressure on a plate.

        Same shape as the member load - RFEM applies a magnitude along one
        direction, so a pressure with several components becomes one load
        object per component.

        The one thing RFEM can do that OpenSees cannot: `projected`. Snow is
        given per square metre of *plan*, not of roof surface, and RFEM has a
        direction enum for it. Ignoring the flag over-loads a flat roof and
        under-loads a steep one.
        """
        if self.Loads is None:
            raise AttributeError("LoadMapper needs the loads module to create surface loads")

        load_type = self._enum(self.Loads.SurfaceLoad, "load_type", "LOAD_TYPE_FORCE")
        distribution = self._enum(
            self.Loads.SurfaceLoad, "load_distribution", "LOAD_DISTRIBUTION_UNIFORM")

        pressure = vector_to_dlubal(surface_load.pressure)
        extent = "PROJECTED_LENGTH" if getattr(surface_load, "projected", False) else "TRUE_LENGTH"
        directions = (
            (pressure.x, "LOAD_DIRECTION_GLOBAL_X_OR_USER_DEFINED_U_{}".format(extent)),
            (pressure.y, "LOAD_DIRECTION_GLOBAL_Y_OR_USER_DEFINED_V_{}".format(extent)),
            (pressure.z, "LOAD_DIRECTION_GLOBAL_Z_OR_USER_DEFINED_W_{}".format(extent)),
        )

        loads = []
        for magnitude, direction_name in directions:
            if not magnitude:
                continue
            loads.append(
                self.Loads.SurfaceLoad(
                    no=self._next_id(),
                    surfaces=[self.numbering.surface(surface_load.surface_id)],
                    load_case=surface_load.load_case_id,
                    load_type=load_type,
                    load_distribution=distribution,
                    load_direction=self._enum(
                        self.Loads.SurfaceLoad, "load_direction", direction_name),
                    # kN/m2 -> N/m2, the same factor as every other force.
                    uniform_magnitude=force_to_dlubal(magnitude),
                )
            )
        return loads

    # -- combinations -------------------------------------------------------

    def map_design_situations(self, combinations):
        """One DesignSituation per combination type in use, in number order.

        Returned before the combinations that reference them; nothing when
        the model has no combinations (the wizard route in design_setup.py
        makes its own).
        """
        wanted = {}
        for combination in combinations:
            number, enum_name, label = design_situation_for(getattr(combination, "combination_type", "ULS"))
            wanted[number] = (enum_name, label)
        objects = []
        for number in sorted(wanted):
            enum_name, label = wanted[number]
            objects.append(self.Loc.DesignSituation(
                no=number,
                name=label,
                design_situation_type=self._enum(self.Loc.DesignSituation, "design_situation_type", enum_name),
                active_for_timber_design=(number == 1),
            ))
        return objects

    def map_load_combination(self, combination):
        """Map a neutral load combination to a Dlubal LoadCombination in its design situation."""
        items_type = self.Loc.LoadCombination.ItemsTable
        row_type = _message_class(items_type.DESCRIPTOR.fields_by_name["rows"].message_type)

        rows = [
            row_type(
                no=index + 1,
                factor=float(factor),
                load_case=int(load_case_id),
            )
            for index, (load_case_id, factor) in enumerate(sorted(combination.factors.items()))
        ]
        situation, _, _ = design_situation_for(getattr(combination, "combination_type", "ULS"))

        return self.Loc.LoadCombination(
            no=combination.id,
            user_defined_name_enabled=True,
            name=combination.name,
            design_situation=situation,
            to_solve=True,
            items=items_type(rows=rows),
        )

    # -- helpers ------------------------------------------------------------

    def _next_id(self):
        load_id = self._load_id_counter
        self._load_id_counter += 1
        return load_id

    @staticmethod
    def _enum(message, field_name, value_name):
        """Resolve an enum value by name, with a clear error if the API changed."""
        enum_type = message.DESCRIPTOR.fields_by_name[field_name].enum_type
        value = enum_type.values_by_name.get(value_name)
        if value is None:
            available = ", ".join(sorted(v.name for v in enum_type.values)[:5])
            raise ValueError(f"{message.DESCRIPTOR.name}.{field_name} has no value {value_name!r}. Available (first 5): {available}")
        return value.number
