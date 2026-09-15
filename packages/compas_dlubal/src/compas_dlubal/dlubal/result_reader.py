from compas_dlubal.dlubal.client import DlubalClient
from compas_dlubal.dlubal.result_parsing import member_lengths_from_model
from compas_dlubal.dlubal.result_parsing import parse_member_deformations
from compas_dlubal.dlubal.result_parsing import parse_member_internal_forces
from compas_dlubal.dlubal.result_parsing import parse_node_deformations
from compas_dlubal.dlubal.result_parsing import parse_support_forces
from compas_timber_fea.core.model import StructuralResultSet


class DlubalResultReader:
    """Reads analysis results from the active Dlubal model into neutral result containers.

    The live surface is deliberately thin: fetch DataFrames via
    get_result_table, then hand them to the pure parsers in result_parsing,
    which are tested offline. Raw column names of every fetched table are kept
    in the result metadata so the parsers' column candidates can be calibrated
    against a real RFEM response.
    """

    def __init__(self, app_type="rfem", api_key=None):
        self.app_type = app_type
        self.api_key = api_key

    def calculate(self, skip_warnings=True):
        """Trigger calculation on the active Dlubal model.

        Returns the name of the application method that was used. Raises a clear
        AttributeError if no known calculation method is available.
        """
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            return self._calculate(conn, [1], skip_warnings=skip_warnings)

    def inspect(self):
        """Return available Dlubal API/application attributes relevant for results."""
        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            return self._inspect(conn)

    def read(self, load_cases=None, calculate=True, structural_model=None):
        """Calculate and read results for the requested load cases.

        Returns {load_case_id: StructuralResultSet} with member internal
        forces, nodal deformations and support reactions. When
        ``structural_model`` is given, member result positions are normalised
        to the 0..1 parameter along each member.
        """
        load_cases = load_cases or [1]
        member_lengths = member_lengths_from_model(structural_model) if structural_model else {}

        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            calculation_method = None
            if calculate:
                calculation_method = self._calculate(conn, load_cases)

            result_sets = {}
            for load_case_id in load_cases:
                result_sets[load_case_id] = self._read_load_case(
                    conn, load_case_id, member_lengths, calculation_method
                )
            return result_sets

    def _read_load_case(self, conn, load_case_id, member_lengths, calculation_method):
        api = conn.api
        application = conn.application
        loading = api.ObjectId(no=load_case_id, object_type=api.OBJECT_TYPE_LOAD_CASE)

        # A failed calculation does not raise - RFEM records it in the
        # errors-and-warnings table and the result queries come back empty.
        # Read that table first, so the message is the solver's, not ours.
        problems = self._solver_problems(conn, load_case_id)
        if problems:
            raise RuntimeError(
                "RFEM calculation failed for load case {}:\n  {}".format(
                    load_case_id, "\n  ".join(problems)))

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
        loading_label = "LC{}".format(load_case_id)

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
            member_results = parse_member_internal_forces(frames["member_forces"], load_case_id, member_lengths)
        if "member_deformations" in frames:
            member_results = parse_member_deformations(frames["member_deformations"], load_case_id, member_lengths, member_results)

        node_results = {}
        if "node_deformations" in frames:
            node_results = parse_node_deformations(frames["node_deformations"], load_case_id)
        if "support_forces" in frames:
            node_results = parse_support_forces(frames["support_forces"], load_case_id, node_results)

        return StructuralResultSet(
            load_case_id=load_case_id,
            name=f"Load Case {load_case_id}",
            node_results=node_results,
            member_results=member_results,
            metadata=metadata,
        )

    def _solver_problems(self, conn, load_case_id):
        """RFEM's errors-and-warnings entries for a load case, formatted; [] when there are none."""
        try:
            api = conn.api
            loading = api.ObjectId(no=load_case_id, object_type=api.OBJECT_TYPE_LOAD_CASE)
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
