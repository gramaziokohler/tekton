"""Loading the numbering from a previous push.

Kept apart from the importer so the import of `BackendMap` is in one place and
the failure modes are named here rather than inside a long `run()`.
"""

from compas_timber_fea.core.backend_map import BackendMap


def load_map(path, backend):
    """The map from a previous push, or a fresh one.

    A missing file is the normal first push, not an error.

    A map belonging to a *different* backend is an error, and a loud one:
    RFEM's object numbers are not SAF's, so using one for the other would bind
    results to the wrong objects without anything failing.
    """
    if not path:
        return BackendMap(backend=backend)
    return BackendMap.load(path, backend=backend)
