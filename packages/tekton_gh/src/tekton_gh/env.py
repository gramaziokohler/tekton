"""Path and environment setup for the Rhino side.

Two ways Tekton reaches Rhino. *Installed*: the components come from the
Package Manager, their `# r: tekton-gh>=X.Y.Z` header has Rhino pip-install
tekton-gh and tekton_core, and there is nothing to find - see
:func:`installed`. *From a checkout*: the components are built from the repo,
and the problem this module solves is that Rhino's Python does not find
`tekton_core`, because the package sits in the monorepo and is not
installed. A repo named explicitly (a `repo` input, or TEKTON_REPO) wins over
an installed Tekton, so a developer can point released components at a
checkout. And the Rhino session may already have imported a *different*
`compas_timber` (the official GH plugin, version 1.0.5) - but Tekton needs the
pinned revision of compas_timber main, which brings `compas_timber.structural`.

Order matters: `sys.path.insert(0, ...)` and, if needed, a purge of the
already loaded modules.
"""

import os
import sys

# Overridden by the components when the repo sits elsewhere.
# Order: explicit argument > environment variable > this default.
DEFAULT_REPO_ENV_VAR = "TEKTON_REPO"

#: Where the last working repo root is remembered, so it survives a Rhino
#: restart. The session variable does not: closing Rhino loses it, and the
#: user has to wire the path in again.
CACHE_FILE = os.path.join(os.path.expanduser("~"), ".tekton", "repo-root")

#: Checkout locations to try when nothing else names one. Each is a guess
#: costing one `isdir` - a few microseconds - never a filesystem search: a
#: `find` over the home directory takes minutes and would run on every solve.
COMMON_LOCATIONS = (
    "~/Documents/GitHub/tekton",
    "~/Documents/git/tekton",
    "~/git/tekton",
    "~/GitHub/tekton",
    "~/Developer/tekton",
    "~/src/tekton",
    "~/tekton",
    "~/Documents/tekton",
    "~/Desktop/tekton",
)

#: Monorepo packages allowed to run inside Rhino (the pure-Python layer).
#: `tekton_dlubal` and `tekton_saf` are deliberately absent - they need
#: grpc/pandas/vtk and only run in the worker (see worker.py).
IN_PROCESS_PACKAGES = ("tekton_core",)


def installed():
    """Is the Rhino side importable without the repo - a Package Manager install?

    `find_spec` only looks, it imports nothing. Once a checkout has been put
    on `sys.path` this is true as well, but TEKTON_REPO is set by then, and
    an explicitly named repo is asked about first.
    """
    import importlib.util

    try:
        return all(importlib.util.find_spec(name) is not None for name in ("tekton_gh",) + IN_PROCESS_PACKAGES)
    except (ImportError, ValueError):
        return False


def _explicit(repo_root):
    """A repo the user named: the argument, or the environment variable."""
    return bool((repo_root and str(repo_root).strip()) or os.environ.get(DEFAULT_REPO_ENV_VAR, "").strip())


def _valid(candidate):
    """Is this a monorepo root?

    Whitespace is stripped first: a Grasshopper panel keeps the newline you
    typed to confirm it, and an invisible "\\n" at the end of an otherwise
    correct path is a needle in a haystack. Shell escaping is *not* undone -
    a panel is not a shell, and "Mobile\\ Documents" really does mean a
    directory with a backslash in its name.
    """
    if not candidate:
        return None
    candidate = os.path.expanduser(str(candidate).strip())
    if not candidate:
        return None
    return candidate if os.path.isdir(os.path.join(candidate, "packages")) else None


def _usable(candidate):
    """Stricter than :func:`_valid`: the packages Rhino needs are really there.

    Used for the guesses. A wrong checkout that merely has a `packages`
    folder would be taken silently and then fail somewhere deep in an import;
    better to insist on what we actually load.
    """
    root = _valid(candidate)
    if root is None:
        return None
    for package in IN_PROCESS_PACKAGES:
        if not os.path.isdir(os.path.join(root, "packages", package, "src")):
            return None
    return root


def _from_cache():
    """The repo root a previous session wrote down."""
    try:
        with open(CACHE_FILE) as handle:
            return _usable(handle.read())
    except (IOError, OSError):
        return None


def _write_cache(root):
    """Remember this root for the next Rhino session. Best effort."""
    try:
        directory = os.path.dirname(CACHE_FILE)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(CACHE_FILE, "w") as handle:
            handle.write(root)
    except (IOError, OSError):
        pass


def _from_document(document_path):
    """Walk up from an open .ghx/.gh file into the repo it may live in.

    The example definitions sit in `packages/tekton_gh/examples/`, so a
    definition opened from the repo names it four levels up. This is the
    guess that works without the user ever having configured anything.
    """
    if not document_path:
        return None
    current = os.path.dirname(os.path.abspath(os.path.expanduser(str(document_path).strip())))
    seen = 0
    while current and seen < 10:
        found = _usable(current)
        if found:
            return found
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        seen += 1
    return None


def document_path_of(ghenv):
    """Path of the Grasshopper definition this component sits in, or None.

    Only useful inside Rhino, and deliberately forgiving: an unsaved
    definition has no path, and every failure here is a missed guess, never
    an error.
    """
    try:
        document = ghenv.Component.OnPingDocument()
        return document.FilePath or None
    except Exception:
        return None


def _from_this_file():
    """Walk up from this very module.

    Only bites when the repo itself is on `sys.path` already - which is the
    case in the worker and in the tests, and never inside Rhino, where this
    module is loaded from the repo *after* the path was found. Harmless and
    occasionally right.
    """
    return _from_document(__file__)


def _from_common_locations():
    for candidate in COMMON_LOCATIONS:
        found = _usable(candidate)
        if found:
            return found
    return None


def discover_repo_root(explicit=None, document_path=None):
    """Find the monorepo without the user having to say where it is.

    The order runs from "told" to "guessed", and every step is cheap - a
    handful of `isdir` calls, never a search. Returns ``(root, source)``,
    where ``source`` names which step produced it, so a component can report
    what it did rather than silently picking a checkout.

    Parameters
    ----------
    explicit : str, optional
        What the user wired into a `repo` input.
    document_path : str, optional
        Path of the open Grasshopper definition, when the caller knows it.

    Returns
    -------
    (str or None, str)
    """
    steps = (
        ("the 'repo' input", lambda: _valid(explicit)),
        ("the {} variable".format(DEFAULT_REPO_ENV_VAR), lambda: _valid(os.environ.get(DEFAULT_REPO_ENV_VAR))),
        ("the open definition", lambda: _from_document(document_path)),
        ("the remembered path ({})".format(CACHE_FILE), _from_cache),
        ("this package's own location", _from_this_file),
        ("a common checkout location", _from_common_locations),
    )
    for source, step in steps:
        try:
            found = step()
        except Exception:      # a guess must never take the session down
            continue
        if found:
            return found, source
    return None, "nowhere"


def remember_repo_root(root):
    """Remember the repo root for the rest of the Rhino session.

    Only a few components have a `repo` input - wiring it into all twenty
    would be nonsense. Whichever one has it and gets a valid path deposits it
    here; all the others find it again.

    It is stored in ``os.environ``, because that applies process-wide and the
    worker subprocess inherits it anyway. The path therefore survives closing
    the definition, but not a Rhino restart - which matches the expectation:
    one canvas works on one repo.
    """
    root = _valid(root)
    if root:
        os.environ[DEFAULT_REPO_ENV_VAR] = root
        _write_cache(root)
    return root


def tekton_repo_root(explicit=None, document_path=None):
    """Determine the root of the Tekton monorepo.

    A thin wrapper over :func:`discover_repo_root` for callers that only want
    the path. The order is: what the user said, what the session or a previous
    session knew, then a few cheap guesses - see there.

    Parameters
    ----------
    explicit : str, optional
        Path set by the user (component input). Wins when set.
    document_path : str, optional
        Path of the open Grasshopper definition, if known.

    Returns
    -------
    str or None
    """
    root, _ = discover_repo_root(explicit, document_path)
    return root


def ensure_tekton_path(repo_root=None, purge_conflicting=True, document_path=None):
    """Make `tekton_core` importable.

    Parameters
    ----------
    repo_root : str, optional
        Repo root; when None, discovered via :func:`discover_repo_root`.
    purge_conflicting : bool
        Drop already loaded `compas_timber` modules from `sys.modules`, so
        the branch version from the active venv wins. In Rhino that is the
        normal case - otherwise the official COMPAS Timber plugin loads
        1.0.5, and `compas_timber.structural` does not exist there.
    document_path : str, optional
        Path of the open Grasshopper definition; lets a definition stored
        inside the repo find it without any configuration.

    Returns
    -------
    str or None
        The repo root that was used, or None for an installed Tekton (no
        repo named, and the packages are importable as they are).

    Raises
    ------
    RuntimeError
        When the repo is not found and Tekton is not installed either. Loud
        on purpose: a component that silently does nothing is worse than one
        that turns red.
    """
    if not _explicit(repo_root) and installed():
        return None
    root, _ = discover_repo_root(repo_root, document_path)
    if root is not None:
        remember_repo_root(root)
    if root is None:
        raise RuntimeError(_not_found_message(repo_root))

    if purge_conflicting:
        _purge("compas_timber")
        _purge("tekton_core")

    for package in IN_PROCESS_PACKAGES:
        src = os.path.join(root, "packages", package, "src")
        if not os.path.isdir(src):
            raise RuntimeError("Expected path missing: {}".format(src))
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)

    return root


def _not_found_message(explicit):
    """Say what was tried, and show the rejected path exactly as it arrived.

    A path that looks right in a panel and is still refused is almost always
    a copied shell path: quotes around it, or "\\ " escaping a space. Printing
    it with repr() makes that visible in one glance instead of an afternoon.
    """
    lines = ["Tekton repo not found."]
    if explicit:
        lines.append("The 'repo' input was {!r} - that is not a monorepo root.".format(str(explicit)))
        stripped = str(explicit).strip()
        if stripped != str(explicit):
            lines.append("Note the whitespace: a Grasshopper panel keeps the newline you typed.")
        if "\\" in stripped or stripped.startswith(('"', "'")):
            lines.append(
                "It carries shell escaping. A panel is not a shell: write the plain path, "
                "spaces as spaces, no quotes and no backslashes.")
    lines.append(
        "Tried, in order: the 'repo' input, ${}, the open definition's folder, "
        "the remembered path, this package's location, and the usual checkout "
        "locations.".format(DEFAULT_REPO_ENV_VAR))
    lines.append(
        "Fix it by wiring the repo path into one component once (TektonInfo, "
        "TektonTranslate, TektonBackend) - it is then remembered for this and "
        "future sessions.")
    return "\n".join(lines)


def _purge(top_level):
    """Throw a top-level package and all its submodules out of `sys.modules`."""
    for name in [m for m in list(sys.modules) if m == top_level or m.startswith(top_level + ".")]:
        del sys.modules[name]


def diagnose(repo_root=None, document_path=None):
    """Status report for the info component.

    Answers the question that comes first in every support case: which
    Python, which compas_timber, is the structural branch there, does it find
    the repo, is there a worker env.

    Returns
    -------
    list of str
    """
    lines = ["Python {}".format(sys.version.split()[0])]

    if not _explicit(repo_root) and installed():
        from tekton_gh import __version__
        from tekton_gh.worker import WORKER_DIR, find_worker_python

        lines.append("Tekton {} (installed, no repo needed)".format(__version__))
        worker = find_worker_python()
        lines.append("Worker: {}".format(worker or "NOT SET UP (expected in {})".format(WORKER_DIR)))
    else:
        root, source = discover_repo_root(repo_root, document_path)
        if root:
            lines.append("Repo: {}".format(root))
            lines.append("      found via {}".format(source))
        else:
            lines.append("Repo: NOT FOUND")

    try:
        import compas

        lines.append("compas {}".format(compas.__version__))
    except ImportError as exc:
        lines.append("compas missing ({})".format(exc))

    try:
        import compas_timber

        lines.append("compas_timber {}".format(compas_timber.__version__))
    except ImportError as exc:
        lines.append("compas_timber missing ({})".format(exc))
        return lines

    try:
        import compas_timber.structural  # noqa: F401

        lines.append("compas_timber.structural: OK")
    except ImportError:
        lines.append(
            "compas_timber.structural MISSING - wrong compas_timber version. "
            "Tekton needs the pinned compas_timber revision; see README."
        )

    try:
        import tekton_core  # noqa: F401

        lines.append("tekton_core: OK")
    except ImportError as exc:
        lines.append("tekton_core not importable ({})".format(exc))

    return lines
