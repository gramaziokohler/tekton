"""Rhino-side test mode.

Rhino 8 runs CPython 3.9 and installs only the Rhino side of Tekton
(tekton_core, tekton-gh). build.yml therefore runs the unit tests a
second time on 3.9 with just those packages, to catch anything that is not
3.9-clean before Rhino's pip does.

Set ``TEKTON_RHINO_SIDE=1`` for that run. A test that needs a worker-only
package (the RFEM client, OpenSees, SAF, the app) is then skipped instead of
failing. Only a missing *worker-only* module is excused: an ImportError from
tekton_core or tekton_gh still fails, because that is exactly what the
run exists to catch. Without the variable nothing here changes anything.
"""

import ast
import os

import pytest

RHINO_SIDE = os.environ.get("TEKTON_RHINO_SIDE") == "1"

#: Top-level modules that only exist in the 3.12 worker environment.
WORKER_ONLY = frozenset(
    (
        "tekton_dlubal",
        "tekton_opensees",
        "tekton_saf",
        "tekton_app",
        "dlubal",
        "grpc",
        "gmsh",
        "openseespy",
        "pandas",
        "openpyxl",
    )
)

HERE = os.path.dirname(os.path.abspath(__file__))


def _top_level_imports(path):
    """Modules a test file imports at module level (not inside functions)."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def _worker_only_modules():
    """Test files that cannot even be imported without the worker packages."""
    ignored = []
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            if _top_level_imports(os.path.join(HERE, name)) & WORKER_ONLY:
                ignored.append(name)
    return ignored


collect_ignore = _worker_only_modules() if RHINO_SIDE else []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Turn a worker-only ModuleNotFoundError inside a test into a skip."""
    outcome = yield
    if not RHINO_SIDE or call.excinfo is None:
        return
    error = call.excinfo.value
    if isinstance(error, ModuleNotFoundError) and (error.name or "").split(".")[0] in WORKER_ONLY:
        report = outcome.get_result()
        report.outcome = "skipped"
        report.longrepr = (str(item.path), item.location[1] or 0, "Rhino side: needs {}".format(error.name))
