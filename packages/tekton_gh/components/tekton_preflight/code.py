"""Tekton Preflight - check the model before calculating.

A model without supports or with disconnected parts otherwise goes into the
analysis without comment and yields nonsense, or a solver abort whose message
nobody reads. Better to notice here.

Thin wrapper around ``compas_timber_fea.core.preflight`` - the checks belong in
the neutral layer, so GUI, CLI and Grasshopper report the same findings. The
Dlubal importer calls the same function on push.

Errors are conditions under which an analysis is meaningless (no supports,
dangling references). Warnings are worth a look (disconnected parts, unused
load cases). Nothing here blocks an export: a push without supports is
legitimate when the engineer adds them in RFEM.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Preflight"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin), which
    knows no `compas_timber.structural`.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
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
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _message(level, text):
    import Grasshopper

    levels = {
        "warning": Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
        "error": Grasshopper.Kernel.GH_RuntimeMessageLevel.Error,
    }
    ghenv.Component.AddRuntimeMessage(levels[level], text)  # type: ignore # noqa: F821


# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
strict: bool  # type: ignore

# --------------------- SCRIPT ---------------------

issues = []
ok = False

if structural is None:
    _message("warning", "No StructuralModel connected.")
else:
    _setup()
    from compas_timber_fea.core.preflight import preflight

    report = preflight(structural)
    ok = report.ok

    for level, text in report:
        issues.append("[{}] {}".format(level, text))

    if not issues:
        issues.append("No findings.")

    if report.errors:
        _message(
            "error" if strict else "warning",
            "{} error(s), {} warning(s). See 'issues'.".format(len(report.errors), len(report.warnings)),
        )
    elif report.warnings:
        _message(
            "error" if strict else "warning",
            "{} warning(s). See 'issues'.".format(len(report.warnings)),
        )

for line in issues:
    print(line)
