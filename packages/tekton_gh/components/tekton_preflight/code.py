"""Tekton Preflight — Modell vor dem Rechnen pruefen.

Ein lagerloses oder unzusammenhaengendes Modell geht sonst kommentarlos
in die Berechnung und liefert Unsinn oder einen Solver-Abbruch, dessen
Meldung niemand liest. Lieber hier auffallen.

Geprueft wird: Auflager vorhanden, Knoten/Staebe vorhanden, Querschnitte
plausibel, keine verwaisten Knoten.
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
strict: bool  # type: ignore

# --------------------- SCRIPT ---------------------

issues = []
ok = False

if structural is None:
    _warn("Kein StructuralModel angeschlossen.")
else:
    _setup()
    from compas_timber_fea.core.units import check_section_plausible

    if not structural.supports:
        issues.append("KRITISCH: Keine Auflager. Das System ist nicht gelagert.")
    if not structural.nodes:
        issues.append("KRITISCH: Keine Knoten.")
    if not structural.members and not structural.surfaces:
        issues.append("KRITISCH: Weder Staebe noch Flaechen.")
    if not structural.load_cases:
        issues.append("Keine Lastfaelle definiert.")

    # Verwaiste Knoten: von keinem Stab und keiner Flaeche referenziert.
    used = set()
    for member in structural.members:
        used.add(member.node_start)
        used.add(member.node_end)
    for surface in structural.surfaces:
        used.update(surface.nodes)
    orphans = [n.id for n in structural.nodes if n.id not in used]
    if orphans:
        issues.append("{} Knoten ohne Anschluss (IDs: {}{}).".format(
            len(orphans), orphans[:8], " ..." if len(orphans) > 8 else ""))

    # Querschnittsmasse: der haeufigste stille Fehler ist ein Einheitenfehler,
    # der Balken 1000-fach zu gross oder zu klein macht.
    # Koppelstaebe ('Rigid') haben bewusst keine Abmessungen — sie sind ein
    # Kunstquerschnitt fuer starre Verbindungen, kein Bauteil.
    rigid_section_ids = set(m.section_id for m in structural.members if m.is_rigid or m.member_type in ("RIGID", "COUPLING"))
    for section in structural.sections:
        if section.id in rigid_section_ids or section.name == "Rigid":
            continue
        note = check_section_plausible(section.width, section.height, units="m")
        if note:
            issues.append("Querschnitt '{}': {}".format(section.name, note))

    critical = [i for i in issues if i.startswith("KRITISCH")]
    ok = not critical

    if issues:
        message = "{} Befund(e), davon {} kritisch.".format(len(issues), len(critical))
        if strict or critical:
            import Grasshopper

            level = (Grasshopper.Kernel.GH_RuntimeMessageLevel.Error if (critical or strict)
                     else Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning)
            ghenv.Component.AddRuntimeMessage(level, message)  # type: ignore # noqa: F821
        else:
            _warn(message)
    else:
        issues.append("Keine Befunde.")
        ok = True

for line in issues:
    print(line)
