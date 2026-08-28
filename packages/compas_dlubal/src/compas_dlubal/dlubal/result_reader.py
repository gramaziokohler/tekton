from compas_dlubal.dlubal.client import DlubalClient
from compas_dlubal.dlubal.result_parsing import member_lengths_from_model
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
            return self._calculate(conn.application, skip_warnings=skip_warnings)

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
                calculation_method = self._calculate(conn.application)

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

        tables = {
            "member_forces": api.results.STATIC_ANALYSIS_MEMBERS_INTERNAL_FORCES,
            "node_deformations": api.results.STATIC_ANALYSIS_NODES_GLOBAL_DEFORMATIONS,
            "support_forces": api.results.STATIC_ANALYSIS_NODES_SUPPORT_FORCES,
        }

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
                result = application.get_result_table(table=table, loading=loading)
                frames[name] = result.data
                metadata["columns"][name] = [str(c) for c in result.data.columns]
                if getattr(result, "warning", ""):
                    metadata.setdefault("warnings", {})[name] = result.warning
            except Exception as error:  # a missing table must not sink the others
                metadata["errors"][name] = f"{type(error).__name__}: {error}"

        member_results = {}
        if "member_forces" in frames:
            member_results = parse_member_internal_forces(frames["member_forces"], load_case_id, member_lengths)

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

    def _calculate(self, application, skip_warnings=True):
        method = getattr(application, "calculate_all", None)
        if not callable(method):
            available = self._public_names(application)
            raise AttributeError(f"No known Dlubal calculation method found. Available application methods: {available}")

        # dlubal.api requires skip_warnings as a keyword-only argument; without it
        # the call raises TypeError before reaching the server.
        method(skip_warnings=skip_warnings)
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
