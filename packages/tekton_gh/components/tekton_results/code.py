"""Tekton Results — Ergebnisse je physischem Balken.

Liefert Huellwerte (was der Entwerfende zuerst sieht) und Stuetzstellen
entlang der Achse (fuer Diagramme). Die Zuordnung laeuft ueber die
Bauteil-GUID: RFEM-Stabnummer -> neutrale Member-ID -> source_element_id
-> Balken. Der analysierte Stab ist nicht der physische Balken — ein
Balken wird in mehrere Staebe geteilt, deren Ergebnisse hier wieder
zusammengefuehrt werden.

Ausnutzung ist die eine Groesse, die noch fehlt: sie kommt aus dem
Bemessungs-Addon von RFEM und ist nicht angebunden. Schnittgroessen,
Verformungen und Auflagerreaktionen werden gelesen.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Results"  # type: ignore # noqa: F821


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
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore
quantity: str  # type: ignore

# --------------------- SCRIPT ---------------------

beam_ids = []
envelope = []
samples = []
stale = False

QUANTITIES = {
    "utilization": None,  # kommt aus dem Bemessungs-Addon, noch ungetestet
    "displacement": "displacement",
    "N": "axial",
    "My": "moment_y",
    "Mz": "moment_z",
    "Vy": "shear_y",
    "Vz": "shear_z",
}

if structural is None:
    _warn("Kein StructuralModel angeschlossen.")
else:
    _setup()

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("Das Modell traegt keine Ergebnisse. Erst TektonRun ausfuehren.")
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)
        if result_set is None:
            _warn("Lastfall {} nicht in den Ergebnissen. Vorhanden: {}.".format(case_id, sorted(results)))
        else:
            key = quantity or "utilization"
            attribute = QUANTITIES.get(key, "displacement")
            if key == "utilization":
                _warn(
                    "Ausnutzung kommt aus dem Bemessungs-Addon von RFEM und ist "
                    "noch nicht angebunden. Es wird die Verformung gezeigt."
                )
                attribute = "displacement"
            elif key not in QUANTITIES:
                _warn("Unbekannte Groesse '{}'. Erlaubt: {}.".format(key, ", ".join(sorted(QUANTITIES))))

            # Member-Ergebnisse ueber die Bauteil-GUID gruppieren: mehrere
            # Staebe gehoeren zum selben physischen Balken.
            member_source = {m.id: m.source_element_id for m in structural.members}
            per_beam = {}
            for member_id, rows in (result_set.member_results or {}).items():
                source = member_source.get(member_id)
                if source is None:
                    continue
                per_beam.setdefault(str(source), []).extend(rows)

            for source, rows in sorted(per_beam.items()):
                values = [abs(getattr(row, attribute, 0.0) or 0.0) for row in rows]
                beam_ids.append(source)
                envelope.append(max(values) if values else 0.0)
                samples.append([(row.position, getattr(row, attribute, 0.0)) for row in rows])

            print("{} Bauteile, Lastfall {}, Groesse '{}'".format(len(beam_ids), case_id, key))

            # Aktualitaet pruefen. Ergebnisse, die still einen aelteren
            # Modellstand beschreiben, sind der gefaehrlichste Fehlermodus
            # dieses Workflows: Grasshopper haelt alte Outputs fest, und eine
            # Zahl sieht nach einer Aenderung genauso richtig aus wie vorher.
            from tekton_gh.worker import model_fingerprint

            metadata = getattr(result_set, "metadata", {}) or {}
            stamped = metadata.get("model_fingerprint")
            if not stamped:
                _warn("Ergebnisse ohne Herkunftsstempel — Aktualitaet nicht pruefbar.")
            else:
                current = model_fingerprint(structural)
                stale = current != stamped
                if stale:
                    _warn(
                        "VERALTET: Die Ergebnisse gehoeren zu Modellstand {}, "
                        "angeschlossen ist {}. Neu rechnen.".format(stamped, current)
                    )
                else:
                    print("Modellstand {} — Ergebnisse aktuell{}.".format(
                        stamped,
                        ", gerechnet {}".format(metadata["calculated_at"]) if metadata.get("calculated_at") else ""))
