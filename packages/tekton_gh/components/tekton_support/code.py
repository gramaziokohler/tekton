"""Tekton Support — Auflagerpunkte auf Balken markieren.

Schreibt `beam.attributes['support_points']`. Das ist heute der einzige
Weg, auf dem der Translator Lager findet: er sucht pro Balken die Punkte,
die innerhalb der Toleranz auf der Achse liegen, und erzeugt dort Knoten
mit gelenkigem Lager.

Die Toleranz ist in Modelleinheiten, nicht in Metern — bei einem
mm-Dokument ist 1e-4 also ein Zehntel Mikrometer. Meist will man hier
einen groesseren Wert.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Support"  # type: ignore # noqa: F821


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
        raise RuntimeError(
            "Tekton-Repo nicht gefunden. Eine Komponente mit 'repo'-Input "
            "(TektonInfo, TektonTranslate, TektonBackend) einmal auf dem Canvas "
            "setzen — der Pfad gilt dann fuer die ganze Sitzung. Siehe TektonInfo."
        )
    # Fuer die Komponenten ohne eigenen repo-Input hinterlegen.
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
model = model  # type: ignore # noqa: F821  TimberModel
points = points  # type: ignore # noqa: F821
support_type: str  # type: ignore
tolerance: float  # type: ignore

# --------------------- SCRIPT ---------------------

found = []
missed = []

if model is None or not points:
    _warn("model und points werden gebraucht.")
else:
    _setup()

    tol = tolerance if tolerance else 1e-4
    support_type = (support_type or "pinned").lower()

    if support_type != "pinned":
        _warn(
            "Lagertyp '{}' angefordert. Der Translator erzeugt heute immer "
            "gelenkige Lager — der Typ wird ignoriert. (TODO: Lagertypen im "
            "neutralen Modell.)".format(support_type)
        )

    # Punkte den Balken zuordnen: ein Punkt gehoert zu dem Balken, auf dessen
    # Mittelachse er (innerhalb der Toleranz) liegt.
    for point in points:
        px, py, pz = point.X, point.Y, point.Z
        matched = False
        for beam in model.beams:
            line = beam.centerline
            start, end = line.start, line.end
            # Abstand Punkt <-> Strecke.
            dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
            length_sq = dx * dx + dy * dy + dz * dz
            if length_sq == 0:
                continue
            t = ((px - start[0]) * dx + (py - start[1]) * dy + (pz - start[2]) * dz) / length_sq
            t = max(0.0, min(1.0, t))
            cx, cy, cz = start[0] + t * dx, start[1] + t * dy, start[2] + t * dz
            distance = ((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2) ** 0.5
            if distance <= tol:
                existing = beam.attributes.get("support_points") or []
                existing.append([px, py, pz])
                beam.attributes["support_points"] = existing
                found.append(point)
                matched = True
                break
        if not matched:
            missed.append(point)

    if missed:
        _warn(
            "{} von {} Punkten liegen auf keiner Balkenachse (Toleranz {}). "
            "Diese Punkte erzeugen KEIN Lager.".format(len(missed), len(points), tol)
        )

    print("{} Auflagerpunkte gesetzt, {} ohne Zuordnung.".format(len(found), len(missed)))
