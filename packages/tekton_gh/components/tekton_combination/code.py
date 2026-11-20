"""Tekton Load Combination - load combination.

Combines load cases with partial safety factors. Manual work today; later an
EC0 generator (permanent/variable, psi factors) would be the real convenience
win.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Combination"  # type: ignore # noqa: F821


def _repo_candidates(explicit):
    """Where to look for the monorepo, cheapest and most certain first.

    Only `isdir` calls - never a filesystem search, this runs on every solve.
    The document guess is what makes a definition stored inside the repo work
    with nothing configured at all; the cache file is what makes the path
    survive a Rhino restart. Mirrors tekton_gh.env.discover_repo_root, which
    cannot be imported yet - finding the repo is what makes it importable.
    """
    yield explicit
    yield os.environ.get("TEKTON_REPO")
    try:
        document = ghenv.Component.OnPingDocument()  # type: ignore # noqa: F821
        current = os.path.dirname(document.FilePath) if document and document.FilePath else None
        for _ in range(8):
            if not current:
                break
            yield current
            parent = os.path.dirname(current)
            current = None if parent == current else parent
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.expanduser("~"), ".tekton", "repo-root")) as handle:
            yield handle.read()
    except Exception:
        pass
    for guess in ("~/Documents/GitHub/tekton", "~/Documents/git/tekton", "~/git/tekton",
                  "~/GitHub/tekton", "~/Developer/tekton", "~/src/tekton", "~/tekton",
                  "~/Documents/tekton", "~/Desktop/tekton"):
        yield guess


def _remember_repo(root):
    """Write the root down so the next Rhino session finds it by itself."""
    try:
        directory = os.path.join(os.path.expanduser("~"), ".tekton")
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, "repo-root"), "w") as handle:
            handle.write(root)
    except Exception:
        pass


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    # Installed from the Package Manager: the `# r:` header has had Rhino
    # pip-install tekton-gh and compas_timber_fea, there is no repo to find.
    # A repo named explicitly (input or TEKTON_REPO) still wins - that is how
    # a developer points released components at a checkout.
    if not (explicit_repo and str(explicit_repo).strip()) and not os.environ.get("TEKTON_REPO"):
        import importlib.util

        if importlib.util.find_spec("compas_timber_fea") and importlib.util.find_spec("tekton_gh"):
            return None
    root = None
    for candidate in _repo_candidates(explicit_repo):
        candidate = str(candidate).strip() if candidate else ""
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
    _remember_repo(root)
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
name: str  # type: ignore
load_cases = load_cases  # type: ignore # noqa: F821
factors = factors  # type: ignore # noqa: F821
combination_type: str  # type: ignore
generate: bool  # type: ignore
favourable: bool  # type: ignore

# --------------------- SCRIPT ---------------------

combination = []
report = []

if not load_cases:
    _warn("Wire the load cases in.")
elif generate:
    # EN 1990 6.10: every variable action leads once, the others enter with
    # psi_0. Plus the serviceability combinations, because deflection limits
    # are checked against those and not against ULS.
    _setup()
    from compas_timber_fea.core.load_catalogue import describe
    from compas_timber_fea.core.load_catalogue import generate_combinations
    from compas_timber_fea.core.load_catalogue import to_load_combinations

    _generated = generate_combinations(list(load_cases), favourable_permanent=bool(favourable))
    combination = to_load_combinations(_generated)
    report = describe(_generated)
    if not combination:
        _warn("Nothing generated - the load cases carry no action categories.")
    for _line in report:
        print(_line)
    print("")
    print("EN 1990 recommended values - NOT verified by an engineer, and not a")
    print("national annex. Use for orientation during design, not verification.")
elif not factors:
    _warn("Give factors, or switch 'generate' on to build the EN 1990 combinations.")
elif len(load_cases) != len(factors):
    _warn("load_cases ({}) and factors ({}) must be the same length.".format(len(load_cases), len(factors)))
else:
    _setup()
    from compas_timber_fea.core.releases import LoadCombination

    _manual = LoadCombination(
        id=1,
        name=name or "Combination",
        factors={getattr(lc, "id", i + 1): float(f) for i, (lc, f) in enumerate(zip(load_cases, factors))},
        combination_type=(combination_type or "ULS").upper(),
    )
    combination = [_manual]
    report = ["{} '{}': {}".format(_manual.combination_type, _manual.name, _manual.factors)]
    print(report[0])
