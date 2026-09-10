"""Erzeugt metadata.json + Platzhalter-Icons für alle Tekton-Komponenten.

Warum generiert und nicht von Hand: die metadata.json des Componentizers ist
sehr geschwätzig (jeder Parameter ~12 Zeilen). Bei 14 Komponenten ist eine
Tabelle plus Generator lesbarer und hält die Konventionen (GUID-Vergabe,
Kategorie, Reihenfolge) automatisch konsistent.

Aufruf (normales Python 3, kein Rhino nötig)::

    python3 _componentizer/build_metadata.py

Danach die Komponenten bauen::

    bash _componentizer/componetize.bash
"""

import json
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENTS_DIR = os.path.join(os.path.dirname(HERE), "components")

CATEGORY = "Tekton"

# Jede Komponente hat eine feste Nummer ("uid"), aus der die InstanceGuid
# gebildet wird. Eine geänderte GUID macht aus einer aktualisierten Komponente
# eine *neue*: bestehende Definitionen verlieren dann ihre Verkabelung. Darum
# sind die Nummern explizit und nicht von der Listenposition abgeleitet —
# umsortieren ist so gefahrlos, nur neu vergeben darf man sie nie.
SUB_SETUP = "0 | Setup"
SUB_AUTHOR = "1 | Author"
SUB_TRANSLATE = "2 | Translate"
SUB_RUN = "3 | Run"
SUB_RESULTS = "4 | Results"
SUB_IO = "5 | IO"


def p(name, hint="ghdoc", access="item", optional=True, desc="", nickname=None):
    """Input-Parameter-Definition (Kurzform)."""
    return {
        "name": name,
        "nickname": nickname or name,
        "description": desc,
        "optional": optional,
        "allowTreeAccess": True,
        "showTypeHints": True,
        "scriptParamAccess": access,
        "wireDisplay": "default",
        "sourceCount": 0,
        "typeHintID": hint,
        "reverse": False,
        "simplify": False,
    }


def o(name, desc="", nickname=None):
    """Output-Parameter-Definition (Kurzform)."""
    return {
        "name": name,
        "nickname": nickname or name,
        "description": desc,
        "optional": False,
        "sourceCount": 0,
        "graft": False,
    }


# --------------------------------------------------------------------------
# Die Komponententabelle. Reihenfolge = Reihenfolge im GH-Menü.
# --------------------------------------------------------------------------

COMPONENTS = [
    # ---------------- Setup ----------------
    dict(
        folder="tekton_info",
        uid=1,
        name="Tekton Info",
        nickname="TInfo",
        sub=SUB_SETUP,
        description=(
            "Zustandsbericht der Tekton-Umgebung: Python-Version, compas_timber-Version, "
            "ob compas_timber.structural vorhanden ist, ob das Repo und das Worker-venv "
            "gefunden werden. Erste Anlaufstelle, wenn eine Komponente rot wird."
        ),
        inputs=[
            p("repo", "str", desc="Pfad zum Tekton-Monorepo. Leer = Umgebungsvariable TEKTON_REPO."),
        ],
        outputs=[o("report", "Diagnose-Zeilen"), o("ok", "True, wenn alles Noetige da ist")],
    ),
    # ---------------- Author ----------------
    dict(
        folder="tekton_material",
        uid=2,
        name="Tekton Material",
        nickname="TMat",
        sub=SUB_AUTHOR,
        description=(
            "Material fuer das Statikmodell waehlen. Heute traegt das neutrale Modell nur "
            "einen Namens-String, den RFEM gegen seine Bibliothek aufloest. Sobald die "
            "Material-Dataclass mit Presets existiert (siehe discussion/materials.md), "
            "liefert diese Komponente ein vollwertiges Material mit Ueberschreibungen."
        ),
        inputs=[
            p("grade", "str", desc="Guetekasse, z.B. 'C24' oder 'GL24h'."),
            p("E0_mean", "float", desc="Optionale Ueberschreibung E0,mean [N/mm2]."),
            p("density", "float", desc="Optionale Ueberschreibung Rohdichte [kg/m3]."),
        ],
        outputs=[o("material", "Material fuer TektonTranslate"), o("info", "Was tatsaechlich gesetzt wurde")],
    ),
    dict(
        folder="tekton_support",
        uid=3,
        name="Tekton Support",
        nickname="TSup",
        sub=SUB_AUTHOR,
        description=(
            "Auflagerpunkte auf Balken markieren. Schreibt beam.attributes['support_points'] — "
            "der einzige Weg, den der Translator heute liest. Die Punkte muessen auf der "
            "Balkenachse liegen (Toleranz 1e-4 in Modelleinheiten)."
        ),
        inputs=[
            p("model", desc="TimberModel (COMPAS Timber).", optional=False),
            p("points", "point", access="list", desc="Auflagerpunkte."),
            p("support_type", "str", desc="'pinned' | 'fixed' | 'roller'. Default: pinned."),
            p("tolerance", "float", desc="Suchradius zur Balkenachse. Default 1e-4 (Modelleinheiten)."),
        ],
        outputs=[
            o("model", "TimberModel mit gesetzten Auflagerattributen"),
            o("found", "Zugeordnete Punkte"),
            o("missed", "Punkte ohne Balken in Reichweite — pruefen!"),
        ],
    ),
    dict(
        folder="tekton_load_case",
        uid=4,
        name="Tekton Load Case",
        nickname="TCase",
        sub=SUB_AUTHOR,
        description=(
            "Lastfall definieren (Eigengewicht, Nutzlast, Schnee, Wind). Lastfaelle sind "
            "die Container, auf die sich Lasten und Kombinationen beziehen."
        ),
        inputs=[
            p("name", "str", desc="Name des Lastfalls."),
            p("category", "str", desc="PERMANENT | VARIABLE | SNOW | WIND."),
            p("self_weight", "bool", desc="Eigengewicht automatisch ansetzen."),
            p("id", "int", desc="Optionale feste ID. Leer = fortlaufend."),
        ],
        outputs=[o("load_case", "Lastfall fuer Translate/Loads")],
    ),
    dict(
        folder="tekton_point_load",
        uid=5,
        name="Tekton Point Load",
        nickname="TPLoad",
        sub=SUB_AUTHOR,
        description=(
            "Einzellast an einem Punkt. Wird beim Anwenden dem naechstgelegenen Knoten des "
            "Statikmodells zugeordnet — die Zuordnung passiert also nach dem Uebersetzen, "
            "weil erst dann Knoten existieren."
        ),
        inputs=[
            p("point", "point", desc="Angriffspunkt."),
            p("force", "vector", desc="Kraft [kN]."),
            p("moment", "vector", desc="Moment [kNm]. Optional."),
            p("load_case", desc="Lastfall aus TektonLoadCase."),
        ],
        outputs=[o("load", "Punktlast fuer TektonApplyLoads")],
    ),
    dict(
        folder="tekton_member_load",
        uid=6,
        name="Tekton Member Load",
        nickname="TMLoad",
        sub=SUB_AUTHOR,
        description=(
            "Streckenlast auf Balken. Die Zuordnung laeuft ueber die Bauteil-GUID, nicht "
            "ueber Stabnummern — ein physischer Balken wird beim Idealisieren in mehrere "
            "Staebe geteilt, die Last muss auf alle davon."
        ),
        inputs=[
            p("beams", access="list", desc="Balken (COMPAS Timber) oder deren GUIDs."),
            p("force", "vector", desc="Streckenlast [kN/m]."),
            p("load_case", desc="Lastfall aus TektonLoadCase."),
            p("start", "float", desc="Relativer Beginn 0..1. Default 0."),
            p("end", "float", desc="Relatives Ende 0..1. Default 1."),
        ],
        outputs=[o("load", "Streckenlast fuer TektonApplyLoads")],
    ),
    dict(
        folder="tekton_combination",
        uid=7,
        name="Tekton Load Combination",
        nickname="TComb",
        sub=SUB_AUTHOR,
        description=(
            "Lastkombination aus Lastfaellen und Teilsicherheitsbeiwerten. "
            "Spaeter: EC0-Generator statt Handarbeit."
        ),
        inputs=[
            p("name", "str", desc="Name, z.B. 'ULS 1'."),
            p("load_cases", access="list", desc="Lastfaelle."),
            p("factors", "float", access="list", desc="Beiwerte, parallel zu load_cases."),
            p("combination_type", "str", desc="ULS | SLS. Default ULS."),
        ],
        outputs=[o("combination", "Kombination fuer TektonApplyLoads")],
    ),
    dict(
        folder="tekton_joint_policy",
        uid=8,
        name="Tekton Joint Policy",
        nickname="TPolicy",
        sub=SUB_AUTHOR,
        description=(
            "Regel, wie Holzverbindungen mechanisch idealisiert werden (gelenkig, steif, "
            "Feder). Das ist eine Ingenieurentscheidung, keine Geometrie — darum explizit, "
            "ueberschreibbar und im Annahmenprotokoll dokumentiert."
        ),
        inputs=[
            p("preset", "str", desc="'conservative' (alles gelenkig) | 'rigid' | 'catalogue'."),
            p("joint_types", "str", access="list", desc="Verbindungstypen, die abweichen sollen."),
            p("releases", "str", access="list", desc="Zugehoerig: 'rigid'|'pinned'|'spherical', parallel zu joint_types."),
        ],
        outputs=[o("policy", "JointPolicy fuer TektonTranslate"), o("info", "Aufgeloeste Regeln")],
    ),
    dict(
        folder="tekton_plate_policy",
        uid=9,
        name="Tekton Plate Policy",
        nickname="TPlatePol",
        sub=SUB_AUTHOR,
        description=(
            "Wie Plattenraender aneinander gekoppelt werden (gelenkige Kante vs. "
            "durchlaufend). Pendant zur Joint Policy fuer den Plattenpfad."
        ),
        inputs=[
            p("preset", "str", desc="'hinged' (Default) | 'continuous'."),
            p("span_direction", "vector", desc="Tragrichtung. Bei Holz nicht optional — Orthotropie."),
        ],
        outputs=[o("policy", "PlateConnectionPolicy fuer TektonTranslate")],
    ),
    # ---------------- Translate ----------------
    dict(
        folder="tekton_apply_loads",
        uid=20,
        name="Tekton Apply Loads",
        nickname="TApply",
        sub=SUB_TRANSLATE,
        description=(
            "Setzt die authorierten Lasten auf das uebersetzte Statikmodell. Muss NACH "
            "TektonTranslate laufen: Punktlasten brauchen Knoten, Streckenlasten brauchen "
            "die Staebe, in die ein Balken zerlegt wurde. Beides existiert vor dem "
            "Uebersetzen noch nicht."
        ),
        inputs=[
            p("structural", desc="StructuralModel aus TektonTranslate.", optional=False),
            p("loads", access="list", desc="Aus TektonPointLoad / TektonMemberLoad."),
            p("combinations", access="list", desc="Aus TektonLoadCombination."),
            p("tolerance", "float", desc="Suchradius Punktlast -> Knoten [m]. Default 0.01."),
        ],
        outputs=[
            o("structural", "StructuralModel mit Lasten"),
            o("report", "Was zugeordnet wurde — und was nicht"),
        ],
    ),
    dict(
        folder="tekton_translate",
        uid=10,
        name="Tekton Translate",
        nickname="TTrans",
        sub=SUB_TRANSLATE,
        description=(
            "Kern der Bruecke: TimberModel -> neutrales StructuralModel. Erzeugt Systemlinien, "
            "Knoten, Querschnitte, Gelenke, Lager. Der 'report'-Ausgang listet alle "
            "getroffenen Annahmen — das ist kein Debug-Output, sondern das, worueber der "
            "Statiker spaeter diskutiert."
        ),
        inputs=[
            p("model", desc="TimberModel (COMPAS Timber).", optional=False),
            p("material", desc="Aus TektonMaterial. Leer = C24."),
            p("joint_policy", desc="Aus TektonJointPolicy. Leer = konservativ (gelenkig)."),
            p("plate_policy", desc="Aus TektonPlatePolicy."),
            p("load_cases", access="list", desc="Aus TektonLoadCase. Leer = nur Eigengewicht."),
            p("units", "str", desc="Einheiten des Timber-Modells. Leer = Rhino-Dokumenteinheit."),
            p("repo", "str", desc="Pfad zum Tekton-Monorepo (siehe TektonInfo)."),
        ],
        outputs=[
            o("structural", "Neutrales StructuralModel"),
            o("report", "Annahmenprotokoll — lesen!"),
            o("preview", "Systemlinien zur Kontrolle"),
        ],
    ),
    dict(
        folder="tekton_preflight",
        uid=11,
        name="Tekton Preflight",
        nickname="TCheck",
        sub=SUB_TRANSLATE,
        description=(
            "Prueft das Statikmodell vor dem Rechnen: Auflager vorhanden? Modell "
            "zusammenhaengend? Querschnitte plausibel? Ein lagerloses Modell geht sonst "
            "kommentarlos in die Berechnung und liefert Unsinn oder einen Solver-Abbruch."
        ),
        inputs=[
            p("structural", desc="StructuralModel aus TektonTranslate.", optional=False),
            p("strict", "bool", desc="True = Fehler statt Warnung bei Befunden."),
        ],
        outputs=[
            o("ok", "True, wenn nichts Kritisches gefunden wurde"),
            o("issues", "Befunde im Klartext"),
        ],
    ),
    # ---------------- Run ----------------
    dict(
        folder="tekton_backend",
        uid=12,
        name="Tekton Backend",
        nickname="TBackend",
        sub=SUB_RUN,
        description=(
            "Backend und Verbindungsdaten buendeln. Der API-Key gehoert NICHT in die "
            "GH-Datei — die wandert per Mail weiter. Leer lassen und die Umgebungsvariable "
            "TEKTON_API_KEY setzen."
        ),
        inputs=[
            p("backend", "str", desc="'rfem' | 'rstab' | 'saf'."),
            p("api_key", "str", desc="Nur fuer Tests. Besser: TEKTON_API_KEY."),
            p("repo", "str", desc="Pfad zum Monorepo (dort liegt das Worker-venv)."),
            p("filepath", "str", desc="Nur bei 'saf': Zielpfad der xlsx-Datei."),
        ],
        outputs=[o("backend", "Backend-Konfiguration fuer TektonRun")],
    ),
    dict(
        folder="tekton_run",
        uid=13,
        name="Tekton Run",
        nickname="TRun",
        sub=SUB_RUN,
        description=(
            "Modell ans Backend schicken, rechnen lassen, Ergebnisse zurueckholen. "
            "Laeuft in einem eigenen Prozess (Backends brauchen Python >= 3.10). "
            "NUR per Button ausloesen — jeder Lauf baut das RFEM-Modell neu auf und "
            "blockiert Grasshopper, solange gerechnet wird."
        ),
        inputs=[
            p("structural", desc="StructuralModel aus TektonTranslate.", optional=False),
            p("backend", desc="Aus TektonBackend.", optional=False),
            p("load_cases", "int", access="list", desc="Lastfaelle, deren Ergebnisse gelesen werden. Leer = alle."),
            p("model_name", "str", desc="Name des Modells im Backend."),
            p("calculate", "bool", desc="False = nur uebergeben, nicht rechnen (Handoff)."),
            p("run", "bool", desc="Button. Ausloesen des Laufs.", optional=False),
        ],
        outputs=[
            o("structural", "Modell mit Ergebnissen"),
            o("log", "Worker-Ausgabe"),
            o("stamp", "Fingerprint + Zeitpunkt des Laufs"),
        ],
    ),
    # ---------------- Results ----------------
    dict(
        folder="tekton_results",
        uid=14,
        name="Tekton Results",
        nickname="TRes",
        sub=SUB_RESULTS,
        description=(
            "Ergebnisse pro physischem Balken auslesen: Huellwerte (max. Ausnutzung, max. "
            "Verformung) und Stuetzstellen entlang der Achse. Die Zuordnung laeuft ueber "
            "die Bauteil-GUID, nicht ueber Stabnummern. Warnt, wenn die Ergebnisse zu "
            "einem aelteren Modellstand gehoeren."
        ),
        inputs=[
            p("structural", desc="StructuralModel mit Ergebnissen (aus TektonRun).", optional=False),
            p("load_case", "int", desc="Lastfall. Leer = erster verfuegbarer."),
            p("quantity", "str", desc="'utilization' | 'displacement' | 'N' | 'My' | 'Vz'."),
        ],
        outputs=[
            o("beam_ids", "Bauteil-GUIDs"),
            o("envelope", "Huellwert je Balken"),
            o("samples", "Stuetzstellen je Balken (t, Wert)"),
            o("stale", "True, wenn die Ergebnisse nicht zum Modell passen"),
        ],
    ),
    dict(
        folder="tekton_attach_results",
        uid=15,
        name="Tekton Attach Results",
        nickname="TAttach",
        sub=SUB_RESULTS,
        description=(
            "Schreibt die Ergebnisse zurueck auf das Timber-Modell "
            "(beam.attributes['analysis']) — mit Herkunftsangabe: welcher Modellstand, "
            "welcher Lastfall, wann. Eine Zahl ohne diese Angabe ist eine Haftungsfrage."
        ),
        inputs=[
            p("model", desc="TimberModel.", optional=False),
            p("structural", desc="StructuralModel mit Ergebnissen.", optional=False),
            p("load_case", "int", desc="Lastfall."),
        ],
        outputs=[o("model", "TimberModel mit Analyse-Attributen"), o("attached", "Anzahl belegter Bauteile")],
    ),
    dict(
        folder="tekton_visualize",
        uid=16,
        name="Tekton Visualize",
        nickname="TViz",
        sub=SUB_RESULTS,
        description=(
            "Faerbt die Bauteile nach einem Ergebniswert ein und liefert eine Legende. "
            "Werte oberhalb der Obergrenze werden hart rot — eine Ueberschreitung soll "
            "auffallen, nicht ausbleichen."
        ),
        inputs=[
            p("structural", desc="StructuralModel mit Ergebnissen.", optional=False),
            p("load_case", "int", desc="Lastfall."),
            p("quantity", "str", desc="'utilization' | 'displacement' | 'N' | 'My' | 'Vz'."),
            p("low", "float", desc="Untergrenze der Skala. Default 0."),
            p("high", "float", desc="Obergrenze. Default 1.0 (= Vollausnutzung)."),
        ],
        outputs=[
            o("geometry", "Systemlinien/Flaechen"),
            o("colours", "Farbe je Element"),
            o("legend", "Beschriftung der Skala"),
        ],
    ),
    dict(
        folder="tekton_inspect",
        uid=17,
        name="Tekton Inspect",
        nickname="TInspect",
        sub=SUB_RESULTS,
        description=(
            "Zeigt das Ersatzsystem selbst: Systemlinien, Knoten, Lagersymbole, "
            "Gelenkmarker. Zum Pruefen der Idealisierung, bevor gerechnet wird — "
            "getrennt von der Ergebnisdarstellung."
        ),
        inputs=[
            p("structural", desc="StructuralModel.", optional=False),
            p("show", "str", access="list", desc="'members' | 'nodes' | 'supports' | 'releases' | 'surfaces'."),
            p("scale", "float", desc="Symbolgroesse in Dokumenteinheiten."),
        ],
        outputs=[
            o("members", "Systemlinien"),
            o("nodes", "Knotenpunkte"),
            o("supports", "Lagersymbole"),
            o("releases", "Gelenkmarker"),
        ],
    ),
    # ---------------- IO ----------------
    dict(
        folder="tekton_save_model",
        uid=18,
        name="Tekton Save Model",
        nickname="TSave",
        sub=SUB_IO,
        description=(
            "Schreibt das neutrale Modell als JSON. Das ist zugleich das Uebergabeformat "
            "an Statiker: nachvollziehbar, versionierbar, diskutierbar — inklusive "
            "Annahmenprotokoll."
        ),
        inputs=[
            p("structural", desc="StructuralModel.", optional=False),
            p("filepath", "str", desc="Zielpfad (.json).", optional=False),
            p("report", "str", access="list", desc="Annahmenprotokoll aus TektonTranslate."),
            p("save", "bool", desc="Button.", optional=False),
        ],
        outputs=[o("path", "Geschriebene Datei")],
    ),
    dict(
        folder="tekton_load_model",
        uid=19,
        name="Tekton Load Model",
        nickname="TLoad",
        sub=SUB_IO,
        description=(
            "Liest ein neutrales Modell (inkl. Ergebnisse) aus JSON zurueck auf den Canvas — "
            "etwa das, was der Statiker zurueckschickt, oder ein frueherer Rechenlauf."
        ),
        inputs=[
            p("filepath", "str", desc="Quelldatei (.json).", optional=False),
            p("repo", "str", desc="Pfad zum Monorepo."),
        ],
        outputs=[
            o("structural", "StructuralModel"),
            o("info", "Kurzuebersicht: Knoten, Staebe, Lastfaelle, Ergebnisse"),
        ],
    ),
]


def make_placeholder_icon(path, seed):
    """24x24-PNG als Platzhalter schreiben (ohne PIL, reines zlib/struct).

    Der Componentizer verlangt eine icon.png; echte Icons kommen spaeter.
    Farbe variiert nach Gruppe, damit die Komponenten im Menue unterscheidbar
    sind, solange nichts Gezeichnetes existiert.
    """
    size = 24
    palette = {
        SUB_SETUP: (110, 110, 120),
        SUB_AUTHOR: (70, 130, 180),
        SUB_TRANSLATE: (60, 150, 110),
        SUB_RUN: (200, 130, 50),
        SUB_RESULTS: (170, 80, 140),
        SUB_IO: (120, 120, 70),
    }
    r, g, b = palette.get(seed, (100, 100, 100))

    rows = []
    for y in range(size):
        row = b"\x00"  # Filtertyp
        for x in range(size):
            border = x < 2 or y < 2 or x >= size - 2 or y >= size - 2
            if border:
                row += bytes((r // 2, g // 2, b // 2, 255))
            else:
                row += bytes((r, g, b, 255))
        rows.append(row)
    raw = b"".join(rows)

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as handle:
        handle.write(png)


def main():
    if not os.path.isdir(COMPONENTS_DIR):
        os.makedirs(COMPONENTS_DIR)

    for spec in COMPONENTS:
        folder = os.path.join(COMPONENTS_DIR, spec["folder"])
        if not os.path.isdir(folder):
            os.makedirs(folder)

        metadata = {
            "name": spec["name"],
            "nickname": spec["nickname"],
            "category": CATEGORY,
            "subcategory": spec["sub"],
            "description": spec["description"],
            "exposure": 2,
            "instanceGuid": "7ec70000-0000-0000-0000-{:012d}".format(spec["uid"]),
            "ghpython": {
                "marshalGuids": True,
                "iconDisplay": 0,
                "inputParameters": spec["inputs"],
                "outputParameters": spec["outputs"],
            },
        }

        with open(os.path.join(folder, "metadata.json"), "w") as handle:
            json.dump(metadata, handle, indent=4)
            handle.write("\n")

        icon_path = os.path.join(folder, "icon.png")
        if not os.path.exists(icon_path):
            make_placeholder_icon(icon_path, spec["sub"])

        print("[x] {:<24} {}".format(spec["folder"], spec["sub"]))

    print("\n{} Komponenten geschrieben nach {}".format(len(COMPONENTS), COMPONENTS_DIR))
    print("Fehlende code.py-Dateien anlegen, dann: bash _componentizer/componetize.bash")


if __name__ == "__main__":
    main()
