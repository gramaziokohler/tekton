"""Tekton Save Model - write the neutral model as JSON.

This is at the same time the handover format for engineers: traceable,
versionable, discussable. Cheaper than arguing about assumptions inside the
RFEM model itself.

The assumptions report from TektonTranslate is put alongside as a text file -
it is part of the handover.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Save"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
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


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
filepath: str  # type: ignore
report = report  # type: ignore # noqa: F821
save: bool  # type: ignore

# --------------------- SCRIPT ---------------------

path = None

if not save:
    print("Ready. Set 'save' to True to write.")
elif structural is None or not filepath:
    _warn("structural and filepath are both needed.")
else:
    _setup()

    target = os.path.expanduser(filepath)
    if not target.lower().endswith(".json"):
        target += ".json"

    folder = os.path.dirname(target)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    structural.to_json(target, pretty=True)
    path = target
    print("Model written: {}".format(target))

    if report:
        report_path = os.path.splitext(target)[0] + "_assumptions.txt"
        with open(report_path, "w") as handle:
            handle.write("\n".join(str(line) for line in report))
            handle.write("\n")
        print("Assumptions report: {}".format(report_path))
    else:
        _warn("No assumptions report connected - a handover should include one.")
