from tekton_dlubal.dlubal.client import DlubalClient
from tekton_dlubal.dlubal.result_parsing import design_ratio_summary
from tekton_dlubal.dlubal.result_parsing import split_design_ratios_by_loading
from tekton_dlubal.dlubal.result_parsing import member_lengths_from_model
from tekton_dlubal.dlubal.result_parsing import parse_member_deformations
from tekton_dlubal.dlubal.result_parsing import parse_member_design_ratios
from tekton_dlubal.dlubal.result_parsing import parse_member_internal_forces
from tekton_dlubal.dlubal.result_parsing import parse_node_deformations
from tekton_dlubal.dlubal.result_parsing import parse_support_forces
from tekton_dlubal.dlubal.result_parsing import parse_surface_results
from tekton_core.core.model import StructuralResultSet
from tekton_core.core.superposition import COMBINATION_ID_BASE


#: What to do when the add-on produced nothing - the one setting the API
#: cannot make (verified 2026-09-18, dlubal.api 2.13.8).
DESIGN_RESULTS_HINT = (
    "No timber design results. RFEM needs the combination wizard's standard group set to "
    "'EN 1990 | Basis + Holz' (Basisangaben > Normen > Lastkombinations-Assistent); the API "
    "cannot set it. Set it once in the GUI, then run again."
)


class DlubalResultReader:
    """Reads analysis results from the active Dlubal model into neutral result containers.

    The live surface is deliberately thin: fetch DataFrames via
    get_result_table, then hand them to the pure parsers in result_parsing,
    which are tested offline. Raw column names of every fetched table are kept
    in the result metadata so the parsers' column candidates can be calibrated
    against a real RFEM response.
    """

    def __init__(self, app_type="rfem", api_key=None, backend_map=None, port=None, model_name=None):
        self.app_type = app_type
        #: The model to calculate and read. RFEM's active model is per
        #: connection, so without a name the reader takes the GUI's - which
        #: may be someone else's model.
        self.model_name = model_name
        self.api_key = api_key
        #: None probes the usual ports; see DlubalClient.
        self.port = port
        #: Translates RFEM's object numbers back to neutral ids. Without
        #: one the two are taken to be the same, which is what every
        #: result read before the BackendMap existed assumed.
        self.backend_map = backend_map

    def calculate(self, skip_warnings=True):
        """Trigger calculation on the active Dlubal model.

        Returns the name of the application method that was used. Raises a clear
        AttributeError if no known calculation method is available.
        """
        with DlubalClient(app_type=self.app_type, api_key=self.api_key, port=self.port) as conn:
            self._select(conn)
            return self._calculate(conn, [1], skip_warnings=skip_warnings)

    def _select(self, conn):
        if self.model_name:
            conn.select_model(self.model_name)

    def inspect(self):
        """Return available Dlubal API/application attributes relevant for results."""
        with DlubalClient(app_type=self.app_type, api_key=self.api_key, port=self.port) as conn:
            return self._inspect(conn)

    def read(self, load_cases=None, calculate=True, structural_model=None, design=False, combinations=None):
        """Calculate and read results for the requested load cases and combinations.

        Returns {result_id: StructuralResultSet} with member internal
        forces, nodal deformations and support reactions. When
        ``structural_model`` is given, member result positions are normalised
        to the 0..1 parameter along each member.

        ``combinations`` are the neutral LoadCombination objects (or their
        ids) the importer pushed; RFEM solves each as loading ``CO<id>`` and
        the result set gets id ``COMBINATION_ID_BASE + id`` - the same id
        ``core.superposition`` would give it, so Summary, Visualize and the
        design checks treat an RFEM-solved combination exactly like an
        assembled one. ``metadata["source"]`` tells them apart.

        With ``design=True`` the timber design add-on's ratio table is read
        as well (``DlubalImporter(design=True)`` sets the add-on up) and
        merged into every result set as ``metadata["utilization"]`` per
        station. The ratio belongs to the add-on's design combination, not
        to the load case - the result-set metadata says which one
        (``metadata["design"]``). A missing ratio table is reported there
        too, not raised: the static results are still worth returning.
        """
        load_cases = load_cases or [1]
        member_lengths = member_lengths_from_model(structural_model) if structural_model else {}
        self._has_surfaces = bool(structural_model.surfaces) if structural_model is not None else True

        with DlubalClient(app_type=self.app_type, api_key=self.api_key, port=self.port) as conn:
            self._select(conn)
            calculation_method = None
            if calculate:
                calculation_method = self._calculate(conn, load_cases)

            result_sets = {}
            for load_case_id in load_cases:
                result_sets[load_case_id] = self._read_loading(
                    conn, "LC", load_case_id, load_case_id, "Load Case {}".format(load_case_id),
                    member_lengths, calculation_method)
            for combination in combinations or []:
                number = int(getattr(combination, "id", combination))
                name = getattr(combination, "name", "") or "Combination {}".format(number)
                result_id = COMBINATION_ID_BASE + number
                result_sets[result_id] = self._read_loading(
                    conn, "CO", number, result_id, name, member_lengths, calculation_method)
                result_sets[result_id].metadata["combination"] = {
                    "id": number,
                    "factors": {int(k): float(v) for k, v in (getattr(combination, "factors", {}) or {}).items()},
                    "combination_type": getattr(combination, "combination_type", ""),
                }
            if design:
                self._read_design_ratios(conn, result_sets, member_lengths)
            return result_sets

    def _read_design_ratios(self, conn, result_sets, member_lengths):
        """Merge the timber design ratio table into every result set."""
        api = conn.api
        try:
            table = api.results.ResultsType.TIMBER_DESIGN_MEMBERS_DESIGN_RATIOS_BY_LOCATION
            result = conn.application.get_results(table)
            frame = result.data
        except Exception as error:
            note = {
                "source": "rfem timber design",
                "error": f"{type(error).__name__}: {error}",
                "hint": DESIGN_RESULTS_HINT,
            }
            for result_set in result_sets.values():
                result_set.metadata["design"] = note
            return

        summary = design_ratio_summary(frame)
        summary["source"] = "rfem timber design"
        summary["columns"] = [str(c) for c in frame.columns]
        summary["rows"] = int(len(frame))
        summary["combinations"] = self._load_combinations(conn)

        # The ratio belongs to a combination. When that combination was read
        # as a result set of its own (authored combinations), it goes there
        # and nowhere else; otherwise (the wizard's own combination) every
        # set gets it, with the metadata saying what it was computed for.
        parts = split_design_ratios_by_loading(frame)
        targets = {COMBINATION_ID_BASE + number: part for number, part in parts.items()
                   if COMBINATION_ID_BASE + number in result_sets}
        if targets:
            for result_id, part in targets.items():
                result_set = result_sets[result_id]
                result_set.member_results = parse_member_design_ratios(
                    part, result_id, member_lengths, result_set.member_results,
                    backend_map=self.backend_map)
                note = dict(summary)
                note["loadings"] = design_ratio_summary(part)["loadings"]
                result_set.metadata["design"] = note
            aside = {"source": summary["source"], "note": "ratios are on the combination result sets",
                     "combinations": summary["combinations"]}
            for result_id, result_set in result_sets.items():
                if result_id not in targets:
                    result_set.metadata["design"] = dict(aside)
            return

        for result_id, result_set in result_sets.items():
            result_set.member_results = parse_member_design_ratios(
                frame, result_id, member_lengths, result_set.member_results,
                backend_map=self.backend_map)
            result_set.metadata["design"] = dict(summary)

    @staticmethod
    def _load_combinations(conn):
        """{"CO1": {"name": "1.35 * LF1", "factors": {1: 1.35}}, ...} - what the design ratios were computed for.

        Best effort: the ratio table only names the combination, and a
        reader of the report needs to know that "CO1" is 1.35 x self-weight
        before comparing it with a load-case ratio.
        """
        api = conn.api
        out = {}
        try:
            ids = conn.application.get_object_id_list(object_type=api.OBJECT_TYPE_LOAD_COMBINATION)
            for object_id in getattr(ids, "object_id", []) or []:
                combination = conn.application.get_object(api.loading.LoadCombination(no=object_id.no))
                out["CO{}".format(object_id.no)] = {
                    "name": combination.name,
                    "factors": {int(row.load_case): float(row.factor) for row in combination.items.rows},
                }
        except Exception:  # informational only
            pass
        return out

    def _read_loading(self, conn, kind, number, result_id, name, member_lengths, calculation_method):
        """One loading - a load case (``kind="LC"``) or a combination (``"CO"``) - into a result set."""
        api = conn.api
        application = conn.application
        object_type = api.OBJECT_TYPE_LOAD_CASE if kind == "LC" else api.OBJECT_TYPE_LOAD_COMBINATION

        # A failed calculation does not raise - RFEM records it in the
        # errors-and-warnings table and the result queries come back empty.
        # Read that table first, so the message is the solver's, not ours.
        problems = self._solver_problems(conn, number, object_type)
        if problems:
            raise RuntimeError(
                "RFEM calculation failed for {}{}:\n  {}".format(
                    kind, number, "\n  ".join(problems)))

        # get_results is the raw database query. get_result_table is the
        # pre-processed table "as displayed in the desktop application" and
        # came back empty for members and nodes on the first live run
        # (2026-09-15), while get_results delivered every row.
        results_type = api.results.ResultsType
        tables = {
            "member_forces": results_type.STATIC_ANALYSIS_MEMBERS_INTERNAL_FORCES,
            "member_deformations": results_type.STATIC_ANALYSIS_MEMBERS_GLOBAL_DEFORMATIONS,
            "node_deformations": results_type.STATIC_ANALYSIS_NODES_GLOBAL_DEFORMATIONS,
            "support_forces": results_type.STATIC_ANALYSIS_NODES_SUPPORT_FORCES,
        }
        # Surface tables only exist for models with surfaces; asking for them
        # otherwise is an error the metadata would record for nothing.
        if getattr(self, "_has_surfaces", True):
            tables["surface_deformations"] = results_type.STATIC_ANALYSIS_SURFACES_GLOBAL_DEFORMATIONS_MESH_NODES
            tables["surface_forces"] = results_type.STATIC_ANALYSIS_SURFACES_BASIC_INTERNAL_FORCES_MESH_NODES
        loading_label = "{}{}".format(kind, number)

        frames = {}
        metadata = {
            "source": "dlubal",
            "app_type": self.app_type,
            "calculation_method": calculation_method,
            "columns": {},
            "errors": {},
        }
        for name, table in tables.items():
            try:
                result = application.get_results(table, loading=loading_label)
                frames[name] = result.data
                metadata["columns"][name] = [str(c) for c in result.data.columns]
                if getattr(result, "warning", ""):
                    metadata.setdefault("warnings", {})[name] = result.warning
            except Exception as error:  # a missing table must not sink the others
                metadata["errors"][name] = f"{type(error).__name__}: {error}"

        member_results = {}
        if "member_forces" in frames:
            member_results = parse_member_internal_forces(frames["member_forces"], result_id, member_lengths, backend_map=self.backend_map)
        if "member_deformations" in frames:
            member_results = parse_member_deformations(frames["member_deformations"], result_id, member_lengths, member_results, backend_map=self.backend_map)

        node_results = {}
        if "node_deformations" in frames:
            node_results = parse_node_deformations(frames["node_deformations"], result_id, backend_map=self.backend_map)
        if "support_forces" in frames:
            node_results = parse_support_forces(frames["support_forces"], result_id, node_results, backend_map=self.backend_map)

        surface_results = {}
        if "surface_deformations" in frames or "surface_forces" in frames:
            surface_results = parse_surface_results(frames.get("surface_deformations"), frames.get("surface_forces"), result_id, backend_map=self.backend_map)

        metadata["loading"] = loading_label
        return StructuralResultSet(
            load_case_id=result_id,
            name=name,
            node_results=node_results,
            member_results=member_results,
            surface_results=surface_results,
            metadata=metadata,
        )

    def _solver_problems(self, conn, load_case_id, object_type=None):
        """RFEM's errors-and-warnings entries for a loading, formatted; [] when there are none."""
        try:
            api = conn.api
            loading = api.ObjectId(no=load_case_id, object_type=object_type or api.OBJECT_TYPE_LOAD_CASE)
            errors = conn.application.get_result_table(
                table=api.results.ERRORS_AND_WARNINGS_TABLE, loading=loading)
        except Exception:  # no table at all is fine - nothing went wrong
            return []
        return self._format_problems(errors.data)

    @staticmethod
    def _format_problems(frame):
        """One line per distinct RFEM error/warning: number, object, description."""
        seen = []
        for _, row in frame.iterrows():
            line = "[{}] {}: {}".format(
                row.get("error_or_warning_number", "?"),
                row.get("object", "?"),
                row.get("description", ""))
            if line not in seen:
                seen.append(line)
        return seen

    def _calculate(self, conn, load_cases, skip_warnings=True):
        application = conn.application
        method = getattr(application, "calculate_all", None)
        if not callable(method):
            available = self._public_names(application)
            raise AttributeError(f"No known Dlubal calculation method found. Available application methods: {available}")

        # dlubal.api requires skip_warnings as a keyword-only argument; without it
        # the call raises TypeError before reaching the server.
        outcome = method(skip_warnings=skip_warnings)

        # A failed calculation does not raise. RFEM answers with a message
        # and, for solver errors, an entry in the errors-and-warnings table -
        # but model errors (a section with no area, say) leave that table
        # empty. has_results() is the one signal that covers both.
        has_results = getattr(application, "has_results", None)
        if callable(has_results):
            available = has_results()
            available = getattr(available, "value", available)
            if not available:
                message = getattr(outcome, "message", "") or "no results after calculation"
                details = []
                for load_case_id in load_cases:
                    details += self._solver_problems(conn, load_case_id)
                if details:
                    message = "\n  ".join([message] + details)
                raise RuntimeError(f"RFEM produced no results: {message}")
        return "calculate_all"

    def _inspect(self, conn):
        api = conn.api
        application = conn.application

        module_names = self._public_names(api)
        likely_result_modules = [name for name in module_names if "result" in name.lower()]

        inspection = {
            "application_methods": self._public_names(application),
            "api_modules": module_names,
            "likely_result_modules": likely_result_modules,
        }

        for module_name in likely_result_modules:
            module = getattr(api, module_name, None)
            inspection[f"{module_name}_attributes"] = self._public_names(module)

        return inspection

    @staticmethod
    def _public_names(obj):
        if obj is None:
            return []
        return sorted(name for name in dir(obj) if not name.startswith("_"))
