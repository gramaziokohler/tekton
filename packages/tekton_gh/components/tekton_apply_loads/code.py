"""Tekton Apply Loads — authorierte Lasten aufs Statikmodell setzen.

Muss **nach** TektonTranslate laufen. Grund: Punktlasten brauchen Knoten,
Streckenlasten brauchen die Stäbe, in die ein physischer Balken zerlegt wurde
— beides entsteht erst beim Übersetzen. Die Author-Komponenten liefern darum
geometrische Beschreibungen (Punkt, Bauteil-GUID), und die Auflösung auf
Modell-IDs passiert hier.

Achtung: Der Dlubal-Importer ignoriert die Lastfälle des neutralen Modells
derzeit noch und verwendet einen fest verdrahteten Katalog (Priorität 1 in
docs/handoff.md). Bis das behoben ist, kommt in RFEM nicht zwingend an, was
hier gesetzt wird.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Apply Loads"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea + tekton_gh importierbar machen."""
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
loads = loads  # type: ignore # noqa: F821
combinations = combinations  # type: ignore # noqa: F821
tolerance: float  # type: ignore

# --------------------- SCRIPT ---------------------

report = []

if structural is None:
    _warn("Kein StructuralModel angeschlossen.")
else:
    _setup()
    from compas_timber_fea.core.model import StructuralMemberLoad, StructuralPointLoad

    tol = 0.01 if tolerance is None else float(tolerance)

    # Skalierung: die Author-Komponenten arbeiten in Dokumenteinheiten (Rhino,
    # typisch mm), das neutrale Modell in Metern.
    units = getattr(structural, "source_units", "m")
    to_meters = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}.get(units, 1.0)

    next_point_id = max([load.id for load in structural.point_loads] or [0]) + 1
    next_member_id = max([load.id for load in structural.member_loads] or [0]) + 1

    # Bauteil-GUID -> alle Stäbe, die daraus entstanden sind. Ein Balken wird
    # beim Idealisieren geteilt; eine Streckenlast muss auf alle Teile.
    by_source = {}
    for member in structural.members:
        by_source.setdefault(str(member.source_element_id), []).append(member.id)

    applied_points = 0
    applied_members = 0

    for load in loads or []:
        if not isinstance(load, dict):
            report.append("Unbekannter Last-Eintrag uebersprungen: {}".format(type(load).__name__))
            continue

        if load.get("kind") == "point":
            position = [value * to_meters for value in load["position"]]
            # Nächstgelegenen Knoten suchen — die Last hängt an einem Punkt,
            # nicht an einer ID.
            best_id, best_distance = None, None
            for node in structural.nodes:
                distance = sum((node.point[i] - position[i]) ** 2 for i in range(3)) ** 0.5
                if best_distance is None or distance < best_distance:
                    best_id, best_distance = node.id, distance

            if best_id is None or best_distance > tol:
                report.append(
                    "Einzellast ohne Knoten in Reichweite (naechster: {:.4g} m, Toleranz {:.4g} m) "
                    "— NICHT gesetzt.".format(best_distance if best_distance is not None else -1, tol)
                )
                continue

            from compas.geometry import Vector

            structural.point_loads.append(
                StructuralPointLoad(
                    id=next_point_id,
                    node_id=best_id,
                    load_case_id=load.get("load_case_id", 1),
                    force=Vector(*load["force"]),
                    moment=Vector(*load.get("moment", [0.0, 0.0, 0.0])),
                )
            )
            next_point_id += 1
            applied_points += 1

        elif load.get("kind") == "member":
            from compas.geometry import Vector

            hit = 0
            for element_id in load.get("element_ids", []):
                member_ids = by_source.get(str(element_id), [])
                if not member_ids:
                    report.append("Bauteil {} hat keine Staebe im Statikmodell.".format(element_id))
                    continue
                for member_id in member_ids:
                    structural.member_loads.append(
                        StructuralMemberLoad(
                            id=next_member_id,
                            member_id=member_id,
                            load_case_id=load.get("load_case_id", 1),
                            force=Vector(*load["force"]),
                            dist_start=load.get("dist_start", 0.0),
                            dist_end=load.get("dist_end", 1.0),
                        )
                    )
                    next_member_id += 1
                    hit += 1
            if hit:
                applied_members += hit

    for combination in combinations or []:
        structural.load_combinations.append(combination)

    report.insert(0, "{} Einzellasten, {} Stablasten gesetzt.".format(applied_points, applied_members))
    if combinations:
        report.insert(1, "{} Kombination(en) uebernommen.".format(len(combinations)))

    report.append(
        "Hinweis: Der Dlubal-Importer nutzt derzeit noch einen fest verdrahteten "
        "Lastkatalog — was hier steht, kommt in RFEM evtl. nicht an "
        "(docs/handoff.md, Punkt 1)."
    )

for line in report:
    print(line)
