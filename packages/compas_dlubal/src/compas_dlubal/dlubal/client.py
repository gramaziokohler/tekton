import os
from typing import Optional

#: Ports to try, in order, when nothing is pinned. RFEM hands out 9000 to the
#: first instance, 9001 to the second and so on, so the port is a property of
#: *this* start of the application, not of the machine - pinning it in a .env
#: goes stale the next time the user opens RFEM alone (seen 2026-09-18 on
#: 9001, 2026-10-13 on 9000).
CANDIDATE_PORTS = (9000, 9001, 9002, 9003)


def configured_port():
    """``DLUBAL_API_PORT`` when set, else None (then the candidates are probed)."""
    raw = os.environ.get("DLUBAL_API_PORT")
    return int(raw) if raw else None


def _is_unreachable(error):
    """True when the error says "nothing is listening there", not "it refused me"."""
    text = str(error)
    return "UNAVAILABLE" in text or "Connection refused" in text or "ConnectEx" in text


class DlubalClient:
    """Verwaltet die Verbindung zur Dlubal API (RFEM/RSTAB)"""
    def __init__(self, app_type: str = "rfem", api_key: Optional[str] = None, port: Optional[int] = None):
        if app_type.lower() == "rstab":
            from dlubal.api import rstab as api
        else:
            from dlubal.api import rfem as api
            
        self.api = api
        self.app_type = app_type
        self.api_key = api_key
        self.port = port or configured_port()
        self._connection = None

    def __enter__(self):
        """Connect, trying the candidate ports when none is pinned.

        A wrong port fails with gRPC UNAVAILABLE - indistinguishable from
        "RFEM is not running" unless the others are tried too, which is the
        error the user actually sees first.
        """
        candidates = [self.port] if self.port else list(CANDIDATE_PORTS)
        last_error = None
        for port in candidates:
            try:
                self._app_context = self.api.Application(api_key_value=self.api_key, port=port)
                self.application = self._app_context.__enter__()
                self.port = port
                return self
            except Exception as error:
                self._app_context = None
                last_error = error
                if not _is_unreachable(error):
                    raise
        ports = ", ".join(str(number) for number in candidates)
        raise RuntimeError(
            "No {} answered on 127.0.0.1:{}. Is the application running, and is its API "
            "enabled (Options > Program Options > API)? A port can be pinned with "
            "DLUBAL_API_PORT or the 'port' input on Tekton Backend.{}{}".format(
                self.app_type.upper(), ports, os.linesep, last_error))

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._app_context:
            self._app_context.__exit__(exc_type, exc_val, exc_tb)

    @property
    def core(self):
        return self.api.structure_core

    @property
    def types_for_nodes(self):
        return self.api.types_for_nodes

    @property
    def loading(self):
        return self.api.loading

    def use_model(self, name):
        """Make the model called ``name`` the active one, creating it if none is open.

        Every push rebuilds its model from scratch (``delete_all``), and the
        API works on whichever model is active - so without this a run wipes
        whatever the user happens to have open, an engineer's model included
        (nearly happened 2026-11-17). The push therefore only ever writes into
        a model of its own name: an open one of that name is activated, else
        a new one is created. Returns ``(name, created)``.
        """
        if not name:
            raise ValueError("use_model needs a model name: the push must not write into whatever is active")
        app = self.application
        models = list(app.get_model_list().model_info)
        active = app.get_active_model()
        active_guid = getattr(active, "guid", None)
        for info in models:
            if info.name == name:
                if info.guid != active_guid:
                    self._set_active(info)
                return name, False
        model_id = app.create_model(name=name)
        self._set_active(model_id)
        return name, True

    def select_model(self, name):
        """Activate the open model called ``name``; never create one, never fall back.

        For reading and calculating: RFEM's active model is per connection
        (a new one starts on the GUI's model again), so the result reader must
        pick its model itself - else it calculates and reads whatever the user
        has in front, an engineer's model included (seen 2026-11-17).
        """
        if not name:
            raise ValueError("select_model needs a model name")
        for info in self.application.get_model_list().model_info:
            if info.name == name:
                self._set_active(info)
                if self.active_model_name() != name:
                    raise RuntimeError("RFEM did not activate model '{}'".format(name))
                return name
        raise RuntimeError("No open RFEM model is called '{}': push it first".format(name))

    def active_model_name(self):
        """Name of the active model, or None."""
        app = self.application
        active = app.get_active_model()
        for info in app.get_model_list().model_info:
            if info.guid == getattr(active, "guid", None):
                return info.name
        return None

    def _set_active(self, model):
        """set_active_model takes the id by keyword in dlubal.api 2.13, positionally in 2.16."""
        from dlubal.api.common.model_id_pb2 import ModelId

        model_id = model if isinstance(model, ModelId) else ModelId(guid=model.guid)
        try:
            self.application.set_active_model(model_id=model_id)
        except TypeError:
            self.application.set_active_model(model_id)

    def delete_all_objects(self):
        """Löscht alle Objekte im aktuellen Modell"""
        self.application.delete_all_objects()

    def create_object_list(self, objects):
        """Sendet eine Liste von Objekten an Dlubal"""
        self.application.create_object_list(objects)
