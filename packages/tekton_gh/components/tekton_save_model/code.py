"""Tekton Save Model — neutrales Modell als JSON schreiben.

Das ist zugleich das Uebergabeformat an Statiker: nachvollziehbar,
versionierbar, diskutierbar. Guenstiger, als im RFEM-Modell selbst
ueber Annahmen zu streiten.

Das Annahmenprotokoll aus TektonTranslate wird als Textdatei daneben
gelegt — es gehoert zur Uebergabe.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Save"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea + tekton_gh importierbar machen.

    Siehe TektonInfo, wenn das fehlschlaegt. Der Purge ist noetig, weil in
    Rhino womoeglich schon ein anderes compas_timber geladen ist (das
    offizielle Plugin, 1.0.5), das kein `compas_timber.structural` kennt.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError("Tekton-Repo nicht gefunden — siehe TektonInfo.")
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
    print("Bereit. 'save' auf True setzen zum Schreiben.")
elif structural is None or not filepath:
    _warn("structural und filepath werden gebraucht.")
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
    print("Modell geschrieben: {}".format(target))

    if report:
        report_path = os.path.splitext(target)[0] + "_annahmen.txt"
        with open(report_path, "w") as handle:
            handle.write("\n".join(str(line) for line in report))
            handle.write("\n")
        print("Annahmenprotokoll: {}".format(report_path))
    else:
        _warn("Kein Annahmenprotokoll angeschlossen — bei einer Uebergabe gehoert es dazu.")
