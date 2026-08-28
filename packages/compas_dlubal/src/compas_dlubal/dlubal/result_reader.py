from compas_dlubal.dlubal.client import DlubalClient
from compas_timber_fea.core.model import StructuralResultSet


class DlubalResultReader:
    """Reads analysis results from the active Dlubal model into neutral result containers.

    The Dlubal Python package exposes generated API objects whose result accessors can
    vary between RFEM/RSTAB versions. This class intentionally starts with connection,
    calculation, and API discovery helpers so result table mapping can be added against
    the concrete installed API.
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

    def read(self, load_cases=None, calculate=True):
        """Calculate and return empty neutral result sets for the requested load cases.

        This establishes the round-trip API shape while the concrete Dlubal result-table
        accessors are identified. The returned result sets include inspection metadata so
        callers can see which result-related API surfaces were available.
        """
        load_cases = load_cases or [1]

        with DlubalClient(app_type=self.app_type, api_key=self.api_key) as conn:
            calculation_method = None
            if calculate:
                calculation_method = self._calculate(conn.application)

            inspection = self._inspect(conn)
            result_sets = {}
            for load_case_id in load_cases:
                result_sets[load_case_id] = StructuralResultSet(
                    load_case_id=load_case_id,
                    name=f"Load Case {load_case_id}",
                    metadata={
                        "source": "dlubal",
                        "app_type": self.app_type,
                        "calculation_method": calculation_method,
                        "inspection": inspection,
                    },
                )
            return result_sets

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
