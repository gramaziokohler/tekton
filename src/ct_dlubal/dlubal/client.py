from typing import Optional

class DlubalClient:
    """Verwaltet die Verbindung zur Dlubal API (RFEM/RSTAB)"""
    def __init__(self, app_type: str = "rfem", api_key: Optional[str] = None):
        if app_type.lower() == "rstab":
            from dlubal.api import rstab as api
        else:
            from dlubal.api import rfem as api
            
        self.api = api
        self.app_type = app_type
        self.api_key = api_key
        self._connection = None

    def __enter__(self):
        self._connection = self.api.Application(api_key_value=self.api_key)
        return self._connection.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._connection:
            self._connection.__exit__(exc_type, exc_val, exc_tb)

    @property
    def core(self):
        return self.api.structure_core

    @property
    def types_for_nodes(self):
        return self.api.types_for_nodes

    @property
    def loading(self):
        return self.api.loading
