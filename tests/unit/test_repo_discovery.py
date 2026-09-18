"""Finding the monorepo without the user having to say where it is.

Two rules the discovery has to keep. It must be *cheap* - a handful of
`isdir` calls, never a filesystem search, because it runs on every solve. And
it must never take a wrong checkout silently: a guess that is not a usable
repo is no guess at all, and whichever step won is reported.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "tekton_gh", "src"))

from tekton_gh import env as env_module  # noqa: E402
from tekton_gh.env import COMMON_LOCATIONS  # noqa: E402
from tekton_gh.env import DEFAULT_REPO_ENV_VAR  # noqa: E402
from tekton_gh.env import discover_repo_root  # noqa: E402
from tekton_gh.env import tekton_repo_root  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No environment variable, no cache, no common location - only what a test sets."""
    monkeypatch.delenv(DEFAULT_REPO_ENV_VAR, raising=False)
    monkeypatch.setattr(env_module, "CACHE_FILE", str(tmp_path / "cache" / "repo-root"))
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", ())
    monkeypatch.setattr(env_module, "_from_this_file", lambda: None)
    return tmp_path


def make_repo(root):
    """A directory that looks like the monorepo to the discovery."""
    for package in env_module.IN_PROCESS_PACKAGES:
        os.makedirs(os.path.join(str(root), "packages", package, "src"))
    return str(root)


# --- the steps, in order -------------------------------------------------

def test_explicit_input_wins(isolated, monkeypatch):
    repo = make_repo(isolated / "explicit")
    other = make_repo(isolated / "other")
    monkeypatch.setenv(DEFAULT_REPO_ENV_VAR, other)
    root, source = discover_repo_root(repo)
    assert root == repo
    assert "repo' input" in source


def test_environment_variable_is_next(isolated, monkeypatch):
    repo = make_repo(isolated / "fromenv")
    monkeypatch.setenv(DEFAULT_REPO_ENV_VAR, repo)
    root, source = discover_repo_root()
    assert root == repo
    assert DEFAULT_REPO_ENV_VAR in source


def test_an_open_definition_inside_the_repo_finds_it(isolated):
    repo = make_repo(isolated / "viadoc")
    examples = os.path.join(repo, "packages", "tekton_gh", "examples")
    os.makedirs(examples)
    document = os.path.join(examples, "tekton_plates_opensees.ghx")
    open(document, "w").close()
    root, source = discover_repo_root(None, document)
    assert root == repo
    assert "definition" in source


def test_the_remembered_path_survives_a_restart(isolated):
    repo = make_repo(isolated / "remembered")
    env_module.remember_repo_root(repo)
    os.environ.pop(DEFAULT_REPO_ENV_VAR, None)          # as if Rhino had restarted
    root, source = discover_repo_root()
    assert root == repo
    assert "remembered" in source


def test_a_common_location_is_the_last_resort(isolated, monkeypatch):
    repo = make_repo(isolated / "common")
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", (repo,))
    root, source = discover_repo_root()
    assert root == repo
    assert "common checkout" in source


def test_nothing_found_is_reported_as_such(isolated):
    root, source = discover_repo_root()
    assert root is None
    assert source == "nowhere"


# --- what must not happen ------------------------------------------------

def test_a_directory_that_is_not_a_repo_is_not_taken(isolated, monkeypatch):
    fake = str(isolated / "notarepo")
    os.makedirs(os.path.join(fake, "packages"))          # has `packages`, nothing else
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", (fake,))
    root, _ = discover_repo_root()
    assert root is None


def test_a_broken_guess_does_not_take_the_session_down(isolated, monkeypatch):
    def explode():
        raise OSError("permission denied")

    repo = make_repo(isolated / "good")
    monkeypatch.setattr(env_module, "_from_cache", explode)
    monkeypatch.setattr(env_module, "COMMON_LOCATIONS", (repo,))
    root, _ = discover_repo_root()
    assert root == repo


def test_discovery_does_not_search_the_filesystem(isolated, monkeypatch):
    """A `find` over the home directory takes minutes; this runs per solve."""
    import os as os_module

    monkeypatch.setattr(os_module, "walk", lambda *a, **k: pytest.fail("discovery must not walk the filesystem"))
    discover_repo_root()


# --- the panel traps -----------------------------------------------------

def test_a_trailing_newline_from_a_panel_is_tolerated(isolated):
    """Enter in a Grasshopper panel keeps the newline in the value."""
    repo = make_repo(isolated / "withnewline")
    root, _ = discover_repo_root(repo + "\n")
    assert root == repo


def test_surrounding_whitespace_is_tolerated(isolated):
    repo = make_repo(isolated / "withspace")
    root, _ = discover_repo_root("  " + repo + "  ")
    assert root == repo


def test_shell_escaping_is_not_silently_accepted(isolated):
    """A panel is not a shell: "Mobile\\ Documents" really means a backslash."""
    repo = make_repo(isolated / "shellish")
    root, _ = discover_repo_root(repo.replace("/", "\\ /", 1))
    assert root is None


def test_the_error_names_the_rejected_path_and_the_cause(isolated):
    """repr() is deliberate: it makes an escaped space or a stray newline
    visible, which is exactly what a plain print would hide."""
    message = env_module._not_found_message("/some/path\\ with/escaping")
    assert repr("/some/path\\ with/escaping") in message
    assert "/some/path" in message
    assert "shell" in message.lower()
    assert DEFAULT_REPO_ENV_VAR in message


def test_the_error_points_out_a_trailing_newline(isolated):
    message = env_module._not_found_message("/some/path\n")
    assert "whitespace" in message.lower() or "newline" in message.lower()


# --- the wrapper ---------------------------------------------------------

def test_tekton_repo_root_returns_just_the_path(isolated, monkeypatch):
    repo = make_repo(isolated / "wrapper")
    monkeypatch.setenv(DEFAULT_REPO_ENV_VAR, repo)
    assert tekton_repo_root() == repo


def test_common_locations_are_plausible_and_expandable():
    assert COMMON_LOCATIONS
    for candidate in COMMON_LOCATIONS:
        assert candidate.startswith("~"), candidate
        assert "tekton" in candidate.lower()
