"""Load cases, loads and combinations, mapped from the neutral model.

Loads are authored in the neutral StructuralModel so that every backend applies
the same loading. This mapper translates that model, rather than defining a
catalogue of its own.
"""

from google.protobuf import symbol_database


def _message_class(descriptor):
    """Resolve a nested protobuf message class from its descriptor.

    Nested row types are not exposed as attributes of their container, so they
    are looked up by their fully qualified name instead.
    """
    return symbol_database.Default().GetSymbol(descriptor.full_name)


#: Neutral action categories -> RFEM action-category enum names.
#: RFEM offers many code-specific variants; these are the plain EN 1990 ones.
ACTION_CATEGORY_NAMES = {
    "PERMANENT": "ACTION_CATEGORY_PERMANENT_G",
    "VARIABLE": "ACTION_CATEGORY_IMPOSED_ACTION_Q",
    "SNOW": "ACTION_CATEGORY_SNOW_ACTION_FSN",
    "WIND": "ACTION_CATEGORY_WIND_QW",
}


class LoadMapper:
    """Maps neutral load cases, loads and combinations to Dlubal objects."""

    def __init__(self, Loc, Loads=None):
        self.Loc = Loc
        # NodalLoad/MemberLoad live in a different proto module than LoadCase.
        self.Loads = Loads
        self._load_id_counter = 1

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

            action_category = self._action_category(load_case.action_category)
            if action_category is not None:
                kwargs["action_category"] = action_category

            objects.append(self.Loc.LoadCase(**kwargs))

        return objects

    def _action_category(self, category):
        """Resolve a neutral action category to the RFEM enum, or None if unavailable."""
        name = ACTION_CATEGORY_NAMES.get((category or "").upper())
        if name is None:
            return None
        enum_type = self.Loc.LoadCase.DESCRIPTOR.fields_by_name["action_category"].enum_type
        value = enum_type.values_by_name.get(name)
        return value.number if value else None

    # -- loads --------------------------------------------------------------

    def map_point_load(self, point_load):
        """Map a nodal force/moment vector to one Dlubal NodalLoad."""
        if self.Loads is None:
            raise AttributeError("LoadMapper needs the loads module to create nodal loads")

        load_type = self._enum(self.Loads.NodalLoad, "load_type", "LOAD_TYPE_COMPONENTS")
        force = point_load.force
        moment = point_load.moment

        load = self.Loads.NodalLoad(
            no=self._next_id(),
            nodes=[point_load.node_id],
            load_case=point_load.load_case_id,
            load_type=load_type,
            components_force_x=float(force.x),
            components_force_y=float(force.y),
            components_force_z=float(force.z),
            components_moment_x=float(moment.x),
            components_moment_y=float(moment.y),
            components_moment_z=float(moment.z),
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

        directions = (
            ("x", member_load.force.x, "LOAD_DIRECTION_GLOBAL_X_OR_USER_DEFINED_U_TRUE_LENGTH"),
            ("y", member_load.force.y, "LOAD_DIRECTION_GLOBAL_Y_OR_USER_DEFINED_V_TRUE_LENGTH"),
            ("z", member_load.force.z, "LOAD_DIRECTION_GLOBAL_Z_OR_USER_DEFINED_W_TRUE_LENGTH"),
        )

        loads = []
        for _axis, magnitude, direction_name in directions:
            if not magnitude:
                continue
            loads.append(
                self.Loads.MemberLoad(
                    no=self._next_id(),
                    members=[member_load.member_id],
                    load_case=member_load.load_case_id,
                    load_type=load_type,
                    load_distribution=distribution,
                    load_direction=self._enum(self.Loads.MemberLoad, "load_direction", direction_name),
                    magnitude=float(magnitude),
                )
            )
        return loads

    # -- combinations -------------------------------------------------------

    def map_load_combination(self, combination):
        """Map a neutral load combination to a Dlubal LoadCombination."""
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

        return self.Loc.LoadCombination(
            no=combination.id,
            name=combination.name,
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
