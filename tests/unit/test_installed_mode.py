"""A Tekton installed from the Package Manager needs no repo checkout.

The released components carry `# r: tekton-gh>=X.Y.Z`, so Rhino pip-installs
tekton-gh and compas_timber_fea before the first solve, and the worker lives
in ~/.tekton/worker. A checkout must keep working exactly as before, and a
repo named explicitly must win over an installed Tekton - that is how a
developer points released components at a checkout. And in installed mode
nothing may be *guessed*: a checkout lying around on the same machine must not
quietly take over.
"""

import ast
import importlib.util
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "tekton_gh", "src"))

from tekton_gh import env as env_module  # noqa: E402
from tekton_gh import worker as worker_module  # noqa: E402

COMPONENTS = pathlib.Path(__file__).resolve().parents[2] / "packages" / "tekton_gh" / "components"


def _fake_find_spec(installed):
    real = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name in ("tekton_gh", "compas_timber_fea"):
            return object() if installed else None
        return real(name, *args, **kwargs)

    return find_spec


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No TEKTON_REPO, no cache, no guesses; sys.path and sys.modules restored.

    sys.modules matters: Tekton Translate's setup purges compas_timber from it
    on purpose (Rhino may have loaded another version), and the rest of the
    test session must keep the classes it already imported.
    """
    monkeypatch.delenv(env_module.DEFAULT_REPO_ENV_VAR, raising=False)
    monkeypatch.delenv(worker_module.WORKER_PYTHON_ENV_VAR, raising=False)
    monkeypatch.setattr(env_module, "CACHE_FILE", str(tmp_path / "cache" / "repo-root"))
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", ())
    monkeypatch.setattr(env_module, "_from_this_file", lambda: None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    modules = dict(sys.modules)
    yield tmp_path
    sys.modules.clear()
    sys.modules.update(modules)


def make_repo(root):
    for package in env_module.IN_PROCESS_PACKAGES:
        os.makedirs(os.path.join(str(root), "packages", package, "src"))
    return str(root)


def make_venv(root):
    """A directory that looks like a venv with a Python in it, on any OS."""
    python = pathlib.Path(root) / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    return str(python)


# --- tekton_gh.env --------------------------------------------------------


def test_installed_needs_no_repo(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    assert env_module.ensure_tekton_path(purge_conflicting=False) is None


def test_an_explicit_repo_wins_over_the_installed_packages(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    repo = make_repo(isolated / "checkout")
    assert env_module.ensure_tekton_path(repo, purge_conflicting=False) == repo
    assert os.path.join(repo, "packages", "compas_timber_fea", "src") in sys.path


def test_tekton_repo_wins_over_the_installed_packages(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    repo = make_repo(isolated / "fromenv")
    monkeypatch.setenv(env_module.DEFAULT_REPO_ENV_VAR, repo)
    assert env_module.ensure_tekton_path(purge_conflicting=False) == repo


def test_installed_does_not_guess_a_checkout(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    guess = make_repo(isolated / "lying-around")
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", (guess,))
    assert env_module.ensure_tekton_path(purge_conflicting=False) is None


def test_a_checkout_still_works_without_an_install(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(False))
    repo = make_repo(isolated / "checkout")
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", (repo,))
    assert env_module.ensure_tekton_path(purge_conflicting=False) == repo


def test_neither_installed_nor_a_checkout_is_loud(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(False))
    with pytest.raises(RuntimeError, match="repo not found"):
        env_module.ensure_tekton_path(purge_conflicting=False)


def test_diagnose_reports_the_installed_mode(isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    monkeypatch.setattr(worker_module, "WORKER_DIR", str(isolated / "no-worker"))
    lines = env_module.diagnose()
    assert any("installed" in line for line in lines)
    assert any("Worker: NOT SET UP" in line for line in lines)
    assert not any(line.startswith("Repo:") for line in lines)


# --- tekton_gh.worker -----------------------------------------------------


def test_the_repo_venv_is_the_worker_for_a_checkout(isolated, monkeypatch):
    monkeypatch.setattr(worker_module, "WORKER_DIR", str(isolated / "home-worker"))
    make_venv(isolated / "home-worker")
    python = make_venv(isolated / "repo" / ".venv")
    assert worker_module.find_worker_python(str(isolated / "repo")) == python


def test_the_home_worker_serves_an_installed_tekton(isolated, monkeypatch):
    monkeypatch.setattr(worker_module, "WORKER_DIR", str(isolated / "home-worker"))
    python = make_venv(isolated / "home-worker")
    assert worker_module.find_worker_python(None) == python


def test_the_environment_variable_overrides_both(isolated, monkeypatch):
    monkeypatch.setattr(worker_module, "WORKER_DIR", str(isolated / "home-worker"))
    make_venv(isolated / "home-worker")
    make_venv(isolated / "repo" / ".venv")
    chosen = make_venv(isolated / "chosen")
    monkeypatch.setenv(worker_module.WORKER_PYTHON_ENV_VAR, chosen)
    assert worker_module.find_worker_python(str(isolated / "repo")) == chosen


def test_no_worker_says_how_to_make_one(isolated, monkeypatch):
    monkeypatch.setattr(worker_module, "WORKER_DIR", str(isolated / "home-worker"))
    with pytest.raises(worker_module.WorkerError) as raised:
        worker_module.worker_python(None)
    message = str(raised.value)
    assert "uv venv --python 3.12" in message
    assert "tekton-app==" in message


def test_a_wrong_environment_variable_is_named(isolated, monkeypatch):
    monkeypatch.setenv(worker_module.WORKER_PYTHON_ENV_VAR, str(isolated / "nope" / "python"))
    with pytest.raises(worker_module.WorkerError, match=worker_module.WORKER_PYTHON_ENV_VAR):
        worker_module.worker_python(None)


# --- the components' own copy of the setup --------------------------------
#
# The components cannot import tekton_gh before they have found it, so each
# carries its own `_setup`. Run every one of them, isolated, in both modes.


def _setup_functions():
    found = []
    for path in sorted(COMPONENTS.glob("*/code.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_setup":
                found.append(pytest.param(ast.get_source_segment(path.read_text(encoding="utf-8"), node), id=path.parent.name))
    return found


def _load(source, candidates):
    namespace = {"os": os, "sys": sys, "_remember_repo": lambda root: None, "_repo_candidates": candidates}
    exec(compile(source, "<_setup>", "exec"), namespace)
    return namespace["_setup"]


@pytest.mark.parametrize("source", _setup_functions())
def test_an_installed_component_does_not_look_for_a_repo(source, isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))

    def must_not_search(explicit):
        raise AssertionError("searched for a repo although Tekton is installed")

    assert _load(source, must_not_search)(None) is None


@pytest.mark.parametrize("source", _setup_functions())
def test_a_checkout_component_still_finds_its_repo(source, isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(False))
    repo = make_repo(isolated / "checkout")
    assert _load(source, lambda explicit: iter([repo]))(None) == repo


@pytest.mark.parametrize("source", _setup_functions())
def test_a_wired_repo_wins_in_a_component(source, isolated, monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec(True))
    repo = make_repo(isolated / "checkout")
    assert _load(source, lambda explicit: iter([explicit]))(repo) == repo


def test_every_component_with_a_repo_search_has_the_installed_check():
    assert len(_setup_functions()) >= 20


def test_every_component_has_exactly_one_header_of_each_kind():
    """`invoke gh-headers` rewrites these two lines in place for a release."""
    for path in sorted(COMPONENTS.glob("*/code.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert sum(line.startswith("# venv:") for line in lines) == 1, path
        assert sum(line.startswith("# r:") for line in lines) == 1, path
