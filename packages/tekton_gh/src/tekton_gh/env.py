"""Path and environment setup for the Rhino side.

The problem this module solves: Rhino's Python does not find
`compas_timber_fea`, because the package sits in the monorepo and is not
installed. And the Rhino session may already have imported a *different*
`compas_timber` (the official GH plugin, version 1.0.5) - but Tekton needs the
`structural_graph_plates` branch, which brings `compas_timber.structural`.

Order matters: `sys.path.insert(0, ...)` and, if needed, a purge of the
already loaded modules.
"""

import os
import sys

# Overridden by the components when the repo sits elsewhere.
# Order: explicit argument > environment variable > this default.
DEFAULT_REPO_ENV_VAR = "TEKTON_REPO"

#: Monorepo packages allowed to run inside Rhino (the pure-Python layer).
#: `compas_dlubal` and `compas_saf` are deliberately absent - they need
#: grpc/pandas/vtk and only run in the worker (see worker.py).
IN_PROCESS_PACKAGES = ("compas_timber_fea",)


def _valid(candidate):
    """Is this a monorepo root?"""
    if not candidate:
        return None
    candidate = os.path.expanduser(str(candidate))
    return candidate if os.path.isdir(os.path.join(candidate, "packages")) else None


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
    return root


def tekton_repo_root(explicit=None):
    """Determine the root of the Tekton monorepo.

    Order: explicit input > what the session remembered > environment
    variable. The first two collapse into the same variable, because
    `remember_repo_root` writes there.

    Parameters
    ----------
    explicit : str, optional
        Path set by the user (component input). Wins when set.

    Returns
    -------
    str or None
    """
    return _valid(explicit) or _valid(os.environ.get(DEFAULT_REPO_ENV_VAR))


def ensure_tekton_path(repo_root=None, purge_conflicting=True):
    """Make `compas_timber_fea` importable.

    Parameters
    ----------
    repo_root : str, optional
        Repo root; when None, looked up via :func:`tekton_repo_root`.
    purge_conflicting : bool
        Drop already loaded `compas_timber` modules from `sys.modules`, so
        the branch version from the active venv wins. In Rhino that is the
        normal case - otherwise the official COMPAS Timber plugin loads
        1.0.5, and `compas_timber.structural` does not exist there.

    Returns
    -------
    str
        The repo root that was used.

    Raises
    ------
    RuntimeError
        When the repo is not found. Loud on purpose: a component that
        silently does nothing is worse than one that turns red.
    """
    root = tekton_repo_root(repo_root)
    if root is not None:
        remember_repo_root(root)
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Set the component's 'repo' input "
            "or the environment variable {}.".format(DEFAULT_REPO_ENV_VAR)
        )

    if purge_conflicting:
        _purge("compas_timber")
        _purge("compas_timber_fea")

    for package in IN_PROCESS_PACKAGES:
        src = os.path.join(root, "packages", package, "src")
        if not os.path.isdir(src):
            raise RuntimeError("Expected path missing: {}".format(src))
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)

    return root


def _purge(top_level):
    """Throw a top-level package and all its submodules out of `sys.modules`."""
    for name in [m for m in list(sys.modules) if m == top_level or m.startswith(top_level + ".")]:
        del sys.modules[name]


def diagnose(repo_root=None):
    """Status report for the info component.

    Answers the question that comes first in every support case: which
    Python, which compas_timber, is the structural branch there, does it find
    the repo, is there a worker env.

    Returns
    -------
    list of str
    """
    lines = ["Python {}".format(sys.version.split()[0])]

    root = tekton_repo_root(repo_root)
    lines.append("Repo: {}".format(root or "NOT FOUND"))

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
            "Tekton needs the 'structural_graph_plates' branch; see README."
        )

    try:
        import compas_timber_fea  # noqa: F401

        lines.append("compas_timber_fea: OK")
    except ImportError as exc:
        lines.append("compas_timber_fea not importable ({})".format(exc))

    return lines
