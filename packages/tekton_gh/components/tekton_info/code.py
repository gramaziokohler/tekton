"""Tekton Info — Zustandsbericht der Umgebung.

Erste Anlaufstelle bei roten Komponenten. Beantwortet: welches Python, welches
compas_timber, ist die structural-Branch da, wird das Repo gefunden, gibt es
ein Worker-venv.

Diese Komponente ist bewusst die einzige, die *ohne* funktionierendes Setup
noch etwas Sinnvolles ausgibt — sie darf nie hart fehlschlagen.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Info"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
repo: str  # type: ignore

# --------------------- SCRIPT ---------------------

report = []
ok = False


def _find_repo(explicit):
    """Repo-Wurzel suchen: Input > Umgebungsvariable."""
    for candidate in (explicit, os.environ.get("TEKTON_REPO")):
        if not candidate:
            continue
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(os.path.join(candidate, "packages")):
            return candidate
    return None


report.append("Python {}".format(sys.version.split()[0]))
if sys.version_info[:2] != (3, 9):
    report.append("  Hinweis: erwartet wurde Rhino 8 / CPython 3.9.")

root = _find_repo(repo)
if root is None:
    report.append("Repo: NICHT GEFUNDEN")
    report.append("  -> Input 'repo' setzen oder Umgebungsvariable TEKTON_REPO.")
else:
    report.append("Repo: {}".format(root))
    # Fuer die Sitzung hinterlegen: die meisten Komponenten haben keinen
    # eigenen repo-Input und wuerden ihn sonst nicht finden.
    os.environ["TEKTON_REPO"] = root

    # Die in Rhino lauffaehige Schicht importierbar machen. compas_dlubal und
    # compas_saf fehlen hier bewusst: die brauchen grpc/pandas/vtk und Python
    # >= 3.10, laufen also nur im Worker-Prozess.
    fea_src = os.path.join(root, "packages", "compas_timber_fea", "src")
    gh_src = os.path.join(root, "packages", "tekton_gh", "src")
    for path in (gh_src, fea_src):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    venv_python = os.path.join(root, ".venv", "bin", "python")
    if not os.path.isfile(venv_python):
        venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_python):
        report.append("Worker-venv: OK")
    else:
        report.append("Worker-venv: FEHLT -> 'uv sync --extra dev' im Repo ausfuehren.")

try:
    import compas

    report.append("compas {}".format(compas.__version__))
except ImportError as exc:
    report.append("compas fehlt ({})".format(exc))

try:
    import compas_timber

    report.append("compas_timber {}".format(compas_timber.__version__))
except ImportError as exc:
    compas_timber = None
    report.append("compas_timber fehlt ({})".format(exc))

if compas_timber is not None:
    try:
        import compas_timber.structural  # noqa: F401

        report.append("compas_timber.structural: OK")
        structural_ok = True
    except ImportError:
        structural_ok = False
        report.append("compas_timber.structural: FEHLT")
        report.append(
            "  -> Falsche compas_timber-Version. Tekton braucht die Branch "
            "'structural_graph_plates'. In Rhino: eigenes venv mit dieser "
            "Revision anlegen (siehe packages/tekton_gh/README.md)."
        )

    if structural_ok:
        try:
            import compas_timber_fea  # noqa: F401

            report.append("compas_timber_fea: OK")
            ok = root is not None
        except ImportError as exc:
            report.append("compas_timber_fea nicht importierbar ({})".format(exc))

report.append("")
report.append("Backends (RFEM/SAF) laufen NICHT hier, sondern im Worker-Prozess:")
report.append("dlubal-api verlangt Python >= 3.10, Rhino faehrt 3.9.")

for line in report:
    print(line)
