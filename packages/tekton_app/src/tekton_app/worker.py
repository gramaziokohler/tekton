"""Backend-Worker: rechnet ausserhalb von Rhino.

Warum es diesen Prozess gibt: ``dlubal-api`` verlangt Python >= 3.10 und zieht
grpcio, pandas und vtk mit; Rhino 8 faehrt CPython 3.9. Der RFEM-Client kann
also prinzipiell nicht in-process in Grasshopper laufen. Die Grenze zwischen
beiden Welten ist die JSON-Serialisierung des neutralen Modells — kein eigenes
Protokoll, und jeder Lauf hinterlaesst nebenbei ein diffbares, uebergabefaehiges
Modell.

Aufruf (so ruft ``tekton_gh.worker.run_backend`` ihn auf)::

    python -m tekton_app.worker model.json --backend rfem --out result.json \
        --model-name "mein-modell" --load-cases 1,3

Der Aufrufer erwartet:

- **stdout** ist das Protokoll; es landet im ``log``-Ausgang der Komponente.
- **Exit-Code 0** heisst Erfolg, alles andere Fehler (stdout wird dann als
  Fehlertext angezeigt).
- Bei allem ausser ``--backend saf`` muss unter ``--out`` ein Modell liegen.

Der API-Key kommt aus ``TEKTON_API_KEY``, sonst aus ``DLUBAL_API_KEY`` -
auch aus der ``.env`` im Arbeitsverzeichnis (dem Repo-Root, so ruft die
GH-Komponente den Worker auf). Er wird nie geloggt.
"""

import argparse
import os
import sys
import time


def load_dotenv(path=".env"):
    """Liest KEY=VALUE-Zeilen aus ``path`` in os.environ, ohne gesetzte zu ueberschreiben.

    Bewusst ohne python-dotenv: die Datei hat drei Zeilen, und der Worker soll
    keine Abhaengigkeit fuer etwas ziehen, das ein Split erledigt.
    """
    if not os.path.isfile(path):
        return
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def read_api_key():
    """TEKTON_API_KEY vor DLUBAL_API_KEY; beide auch aus der .env."""
    load_dotenv()
    return os.environ.get("TEKTON_API_KEY") or os.environ.get("DLUBAL_API_KEY") or None


def log(message):
    """Nach stdout, ungepuffert — der Aufrufer liest das Protokoll am Stueck."""
    print(message)
    sys.stdout.flush()


def unbuffer_stdout():
    """Ausgaben in der Reihenfolge halten, in der sie entstehen.

    Der Aufrufer sammelt stdout und stderr in einem Strom. Ohne das hier
    erscheinen gepufferte ``print``-Zeilen aus den Bibliotheken (etwa der
    Preflight-Bericht des Importers) *nach* einer Fehlermeldung, die
    ungepuffert durchkommt — und der Leser schliesst auf die falsche
    Ursache.
    """
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:  # aeltere Interpreter
        pass


def parse_load_cases(raw):
    """"1,3" -> [1, 3]. Leer/None -> None (= alle)."""
    if not raw:
        return None
    cases = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            cases.append(int(chunk))
        except ValueError:
            raise SystemExit("--load-cases erwartet ganze Zahlen, bekam: {!r}".format(chunk))
    return cases or None


def run_saf(model, out_path, model_name):
    """SAF-Export. Schreibt eine xlsx, kein Ergebnismodell."""
    from tekton_saf.exporter.saf import SAFExporter

    target = out_path
    if not target.lower().endswith(".xlsx"):
        target = os.path.splitext(target)[0] + ".xlsx"

    log("SAF-Export nach {}".format(target))
    from tekton_saf.exporter.saf import UnsupportedModel

    exporter = SAFExporter(model)
    try:
        exporter.export(target)
    except UnsupportedModel as error:
        # A SAF file that drops releases or surfaces looks right and is a
        # different structure. Say what and why, rather than writing it.
        log(str(error))
        raise
    if exporter.report and exporter.report.warnings:
        for warning in exporter.report.warnings:
            log("SAF does not carry: {}".format(warning))
    log("SAF-Datei geschrieben.")
    return None


def run_opensees(model, load_cases, calculate, mesh_target_length=None):
    """Modell mit OpenSees rechnen - im Prozess, ohne Lizenz, ohne Key.

    ``mesh_target_length`` steuert die Zielkantenlaenge der Plattenvernetzung
    in Metern. Sie ist ein Hinweis an den Vernetzer, kein Modellwert: eine
    feinere Vorgabe kostet Rechenzeit und aendert das Ergebnis nur, solange
    es noch nicht konvergiert ist.
    """
    from tekton_opensees import run_model

    if not calculate:
        log("OpenSees hat keinen Modellzustand ohne Rechnung - --no-calculate ist hier bedeutungslos.")
        return model

    started = time.time()
    runner = run_model(model, load_cases=load_cases, mesh_target_length=mesh_target_length)
    for line in runner.log:
        log("  " + line)
    log("Berechnung abgeschlossen ({:.2f}s).".format(time.time() - started))
    for case_id, result_set in sorted(model.results.items()):
        log("  Lastfall {}: {} Staebe, {} Knoten".format(case_id, len(result_set.member_results or {}), len(result_set.node_results or {})))
    return model


def run_dlubal(model, app_type, model_name, load_cases, calculate, api_key, delete_all, design=False, port=None):
    """Modell nach RFEM/RSTAB schieben, rechnen, Ergebnisse zurueckholen.

    Mit ``design`` wird nach dem Push das Holzbemessungs-Add-on eingerichtet
    und dessen Ausnutzung pro Station mitgelesen (``metadata["utilization"]``).
    """
    from tekton_dlubal.dlubal.importer import DlubalImporter
    from tekton_dlubal.dlubal.result_reader import DlubalResultReader

    log("Verbinde mit {} …".format(app_type.upper()))
    importer = DlubalImporter(app_type=app_type, api_key=api_key, delete_all=delete_all, design=design, port=port)

    started = time.time()
    if not importer.run(model, model_name=model_name):
        raise SystemExit("Push nach {} fehlgeschlagen.".format(app_type.upper()))
    log("Modell uebertragen ({:.1f}s).".format(time.time() - started))

    if not calculate:
        log("Nicht gerechnet (--no-calculate): Modell liegt im Backend zur Weiterbearbeitung.")
        return model

    # Ohne explizite Auswahl alle Lastfaelle des Modells lesen. Der Reader
    # faellt sonst auf [1] zurueck, was bei mehreren Faellen stillschweigend
    # zu wenig waere.
    cases = load_cases or [case.id for case in model.load_cases] or [1]
    log("Rechnen und Ergebnisse lesen fuer Lastfall/-faelle {} …".format(cases))

    started = time.time()
    # The same numbering the push used: RFEM reports its own object numbers,
    # and without the map they would be read back as neutral ids - which they
    # have not been since the ids became hashes.
    reader = DlubalResultReader(app_type=app_type, api_key=api_key,
                                backend_map=importer.backend_map, port=port, model_name=model_name)
    combinations = list(model.load_combinations or [])
    if combinations:
        log("  plus {} Kombination(en), von RFEM geloest: {}".format(
            len(combinations), ", ".join("CO{}".format(c.id) for c in combinations)))
    model.results = reader.read(load_cases=cases, calculate=True, structural_model=model, design=design,
                                combinations=combinations)
    log("Berechnung abgeschlossen ({:.1f}s).".format(time.time() - started))
    if design:
        note = next(iter(model.results.values())).metadata.get("design", {}) if model.results else {}
        if note.get("error"):
            log("  Holzbemessung: keine Ergebnisse - {}".format(note.get("hint", note["error"])))
        else:
            log("  Holzbemessung: {} Zeilen fuer Kombination(en) {}".format(note.get("rows"), ", ".join(note.get("loadings", []))))

    for case_id, result_set in sorted(model.results.items()):
        metadata = getattr(result_set, "metadata", {}) or {}
        log("  Lastfall {}: {} Staebe, {} Knoten, {} Flaechen".format(
            case_id, len(result_set.member_results or {}), len(result_set.node_results or {}),
            len(getattr(result_set, "surface_results", None) or {})))
        # Fehlende Ergebnistabellen sind der haeufigste stille Teilausfall:
        # eine Tabelle fehlt, die anderen kommen durch, und niemand merkt es.
        for table, error in (metadata.get("errors") or {}).items():
            log("    Tabelle '{}' nicht gelesen: {}".format(table, error))

    return model


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tekton_app.worker",
        description="Neutrales Statikmodell an ein Backend schicken und Ergebnisse zurueckschreiben.",
    )
    parser.add_argument("input", help="Pfad zum serialisierten StructuralModel (.json)")
    parser.add_argument("--backend", default="rfem", choices=["rfem", "rstab", "saf", "opensees"])
    parser.add_argument("--out", help="Zielpfad. Bei rfem/rstab das Ergebnismodell (.json), bei saf die .xlsx")
    parser.add_argument("--model-name", default="tekton", help="Modellname im Backend")
    parser.add_argument("--load-cases", help="Kommaliste, z.B. '1,3'. Leer = alle Lastfaelle des Modells")
    parser.add_argument("--no-calculate", action="store_true", help="Nur uebertragen, nicht rechnen")
    parser.add_argument("--delete-all", action="store_true", help="Backend-Modell vor dem Push leeren")
    parser.add_argument("--design", action="store_true", help="rfem: Holzbemessungs-Add-on einrichten und Ausnutzung mitlesen")
    parser.add_argument("--port", type=int, default=None,
                        help="rfem/rstab: gRPC-Port der laufenden Anwendung. Ohne Angabe werden 9000-9003 probiert.")
    parser.add_argument("--mesh-size", type=float, default=None,
                        help="opensees: Zielkantenlaenge der Plattenvernetzung in Metern (Default 0.5)")

    args = parser.parse_args(argv)
    unbuffer_stdout()

    if not os.path.isfile(args.input):
        raise SystemExit("Eingabedatei nicht gefunden: {}".format(args.input))
    if not args.out:
        raise SystemExit("--out wird gebraucht.")

    # Erst importieren, wenn die Argumente stimmen: der Import zieht grpc/vtk
    # und dauert spuerbar.
    from tekton_core.core.model import StructuralModel

    log("Lade Modell: {}".format(args.input))
    model = StructuralModel.from_json(args.input)
    log("{} Knoten, {} Staebe, {} Flaechen, {} Lager, {} Lastfaelle".format(
        len(model.nodes), len(model.members), len(model.surfaces),
        len(model.supports), len(model.load_cases)))

    # Der Key wird bewusst nie geloggt.
    api_key = read_api_key()
    if args.backend in ("rfem", "rstab"):
        log("API-Key: {}".format(
            "gesetzt" if api_key else "nicht gesetzt (TEKTON_API_KEY, DLUBAL_API_KEY oder .env im Repo)"))

    if args.backend == "saf":
        result_model = run_saf(model, args.out, args.model_name)
    elif args.backend == "opensees":
        result_model = run_opensees(model, parse_load_cases(args.load_cases), not args.no_calculate,
                                    mesh_target_length=args.mesh_size)
    else:
        result_model = run_dlubal(
            model,
            app_type=args.backend,
            model_name=args.model_name,
            load_cases=parse_load_cases(args.load_cases),
            calculate=not args.no_calculate,
            api_key=api_key,
            delete_all=args.delete_all,
            design=args.design and args.backend == "rfem",
            port=args.port,
        )

    if result_model is not None:
        folder = os.path.dirname(os.path.abspath(args.out))
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        result_model.to_json(args.out, pretty=True)
        log("Ergebnismodell geschrieben: {}".format(args.out))

    log("Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
