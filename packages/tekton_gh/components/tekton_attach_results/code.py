"""Tekton Attach Results — Ergebnisse zurueck aufs Timber-Modell.

Schreibt `beam.attributes['analysis']` mit Huellwerten, Stuetzstellen
und Herkunftsangabe.

Die Herkunft ist Pflicht, nicht Kuer: eine Zahl ohne 'welcher
Modellstand, welche Kombination, wann' ist eine Haftungsfrage. Der
schlimmste Fehlermodus ist, dass Ergebnisse eine Entwurfsaenderung
still ueberleben.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Attach"  # type: ignore # noqa: F821


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
model = model  # type: ignore # noqa: F821
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore

# --------------------- SCRIPT ---------------------

attached = 0

if model is None or structural is None:
    _warn("model und structural werden gebraucht.")
else:
    _setup()
    import time

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("Keine Ergebnisse im Modell — erst TektonRun ausfuehren.")
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)

        if result_set is None:
            _warn("Lastfall {} nicht vorhanden.".format(case_id))
        else:
            member_source = {m.id: str(m.source_element_id) for m in structural.members}
            per_beam = {}
            for member_id, rows in (result_set.member_results or {}).items():
                source = member_source.get(member_id)
                if source is None:
                    continue
                per_beam.setdefault(source, []).extend(rows)

            provenance = {
                "load_case": case_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": (getattr(result_set, "metadata", {}) or {}).get("source", "unknown"),
            }

            for beam in model.beams:
                rows = per_beam.get(str(beam.guid))
                if not rows:
                    continue
                beam.attributes["analysis"] = {
                    "provenance": provenance,
                    "samples": [
                        (row.position, {
                            "N": row.axial, "Vy": row.shear_y, "Vz": row.shear_z,
                            "Mt": row.torsion, "My": row.moment_y, "Mz": row.moment_z,
                            "displacement": row.displacement,
                        })
                        for row in rows
                    ],
                    "envelope": {
                        "max_displacement": max((abs(r.displacement or 0.0) for r in rows), default=0.0),
                        "max_moment_y": max((abs(r.moment_y or 0.0) for r in rows), default=0.0),
                        # TODO(scaffold): max_utilization, sobald das
                        # Bemessungs-Addon angebunden ist.
                    },
                }
                attached += 1

            print("Ergebnisse an {} von {} Bauteilen.".format(attached, len(list(model.beams))))
            if attached == 0:
                _warn(
                    "Kein Bauteil getroffen. Meist stimmen die Bauteil-GUIDs nicht "
                    "mehr — das Timber-Modell wurde nach dem Rechnen veraendert."
                )
