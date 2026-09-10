"""Tekton Preflight — Modell vor dem Rechnen pruefen.

Ein lagerloses oder unzusammenhaengendes Modell geht sonst kommentarlos in die
Berechnung und liefert Unsinn oder einen Solver-Abbruch, dessen Meldung niemand
liest. Lieber hier auffallen.

Duenner Wrapper um ``compas_timber_fea.core.preflight`` — die Pruefungen
gehoeren in die neutrale Schicht, damit GUI, CLI und Grasshopper dieselben
Befunde melden. Der Dlubal-Importer ruft dieselbe Funktion beim Push.

Fehler ("error") sind Bedingungen, unter denen eine Berechnung sinnlos ist
(keine Auflager, ins Leere zeigende Verweise). Warnungen sind einen Blick wert
(unverbundene Teile, ungenutzte Lastfaelle). Nichts davon blockiert einen
Export: ein Push ohne Auflager ist legitim, wenn der Statiker sie in RFEM
ergaenzt.
"""
# venv: tekton
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Preflight"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea + tekton_gh importierbar machen.

    Siehe TektonInfo, wenn das fehlschlaegt. Der Purge ist noetig, weil in
    Rhino womoeglich schon ein anderes compas_timber geladen ist (das
    offizielle Plugin), das kein `compas_timber.structural` kennt.
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
    _message("warning", "Kein StructuralModel angeschlossen.")
else:
    _setup()
    from compas_timber_fea.core.preflight import preflight

    report = preflight(structural)
    ok = report.ok

    for level, text in report:
        issues.append("[{}] {}".format(level, text))

    if not issues:
        issues.append("Keine Befunde.")

    if report.errors:
        _message(
            "error" if strict else "warning",
            "{} Fehler, {} Warnung(en). Siehe 'issues'.".format(len(report.errors), len(report.warnings)),
        )
    elif report.warnings:
        _message(
            "error" if strict else "warning",
            "{} Warnung(en). Siehe 'issues'.".format(len(report.warnings)),
        )

for line in issues:
    print(line)
