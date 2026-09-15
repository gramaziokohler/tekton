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
    from compas_saf.exporter.saf import SAFExporter

    target = out_path
    if not target.lower().endswith(".xlsx"):
        target = os.path.splitext(target)[0] + ".xlsx"

    log("SAF-Export nach {}".format(target))
    SAFExporter(model).export(target)
    log("SAF-Datei geschrieben.")
    return None


def run_dlubal(model, app_type, model_name, load_cases, calculate, api_key, delete_all):
    """Modell nach RFEM/RSTAB schieben, rechnen, Ergebnisse zurueckholen."""
    from compas_dlubal.dlubal.importer import DlubalImporter
    from compas_dlubal.dlubal.result_reader import DlubalResultReader

    log("Verbinde mit {} …".format(app_type.upper()))
    importer = DlubalImporter(app_type=app_type, api_key=api_key, delete_all=delete_all)

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
    reader = DlubalResultReader(app_type=app_type, api_key=api_key)
    model.results = reader.read(load_cases=cases, calculate=True, structural_model=model)
    log("Berechnung abgeschlossen ({:.1f}s).".format(time.time() - started))

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
    parser.add_argument("--backend", default="rfem", choices=["rfem", "rstab", "saf"])
    parser.add_argument("--out", help="Zielpfad. Bei rfem/rstab das Ergebnismodell (.json), bei saf die .xlsx")
    parser.add_argument("--model-name", default="tekton", help="Modellname im Backend")
    parser.add_argument("--load-cases", help="Kommaliste, z.B. '1,3'. Leer = alle Lastfaelle des Modells")
    parser.add_argument("--no-calculate", action="store_true", help="Nur uebertragen, nicht rechnen")
    parser.add_argument("--delete-all", action="store_true", help="Backend-Modell vor dem Push leeren")

    args = parser.parse_args(argv)
    unbuffer_stdout()

    if not os.path.isfile(args.input):
        raise SystemExit("Eingabedatei nicht gefunden: {}".format(args.input))
    if not args.out:
        raise SystemExit("--out wird gebraucht.")

    # Erst importieren, wenn die Argumente stimmen: der Import zieht grpc/vtk
    # und dauert spuerbar.
    from compas_timber_fea.core.model import StructuralModel

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
    else:
        result_model = run_dlubal(
            model,
            app_type=args.backend,
            model_name=args.model_name,
            load_cases=parse_load_cases(args.load_cases),
            calculate=not args.no_calculate,
            api_key=api_key,
            delete_all=args.delete_all,
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
