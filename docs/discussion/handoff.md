# Tekton — Kurzübersicht

*Stand: 2026-09-15*

## Was es ist

Eine Brücke von **COMPAS Timber** (Holzbau-Entwurfsmodelle) zu **Statiksoftware**,
zuerst Dlubal RFEM/RSTAB über deren neue gRPC-API, zusätzlich SAF-Export als
dateibasierter Weg.

Der Kern der Aufgabe ist keine Formatkonvertierung, sondern eine **Idealisierung**:
Ein Timber-Modell beschreibt physische Bauteile und Fügungen, ein Statikmodell ein
mechanisches Ersatzsystem (Systemlinien, Knoten, Gelenke, Federn, Lasten). Dazwischen
liegen Ingenieurentscheidungen, die nicht aus der Geometrie ableitbar sind.

### Core questions this tries to adress

- How to derive an **idealized structural model** from a COMPAS Timber model
- Methods of **storing** said model
- How to **communicate** it to **other software**

## Wozu

Zwei Nutzungsmodi, bewusst getrennt:

- **Designer-Loop** — RFEM als Rechenmaschine: Modell hin, rechnen, Kennwerte
  zurück (Verformung, Ausnutzung). Erlaubt Entwerfenden, früh Performance-Werte
  zu bekommen, ohne selbst in Statiksoftware zu modellieren.
- **Handoff an Statiker** — das erzeugte Modell ist Arbeitsgrundlage für
  Fachleute; komplexes Nachmodellieren entfällt.

Abgrenzung zu COMPAS FEA2: thematische Überlappung, aber FEA2 ist generisch und
kontinuumsorientiert. Der Wert hier liegt in der **holzspezifischen
Idealisierungsschicht** (Fügung → Mechanik, Systemlinien). Eine Auflösung ineinander
ist derzeit nicht geplant; FEA2 wäre perspektivisch ein weiterer Backend-Adapter.

## Aufbau

Monorepo (uv-Workspace), vier Pakete:

```text
TimberModel  →  StructuralModel (neutral)  →  Backend-Adapter  →  RFEM / SAF
```

| Paket | Rolle |
|---|---|
| `compas_timber_fea` | **Neutrale Schicht.** Übersetzt Timber → `StructuralModel` (Knoten, Stäbe, Flächen, Gelenke, Lager, Lasten). Enthält Joint-Policy, Einheiten-Vertrag, Serialisierung. |
| `compas_dlubal` | Dlubal-Adapter: gRPC-Client, ein Mapper pro Objekttyp, Ergebnis-Reader (live gegen RFEM 6 verifiziert). |
| `compas_opensees` | OpenSees-Adapter (openseespy, pip-installierbar, kein Lizenzserver): Balken, Gelenke/Federn, Lasten, Eigengewicht, Ergebnisse an 9 Stationen. Gegen RFEM kalibriert; die ganze Kette läuft damit in CI. Platten noch nicht. |
| `compas_saf` | SAF-Export (xlsx) — Handoff ohne Live-Verbindung. |
| `tekton_app` | GUI (PySide6) + CLI für Nutzer ohne Python; `tekton_app.worker` ist der Subprozess, den Grasshopper aufruft. |
| `tekton_gh` | Grasshopper-Komponenten (Rhino 8, CPython 3.9): Authoring, Translate, Preflight, Run, Results, Visualize. Spricht mit dem Worker über JSON-Dateien, weil `dlubal-api` Python ≥ 3.10 braucht. |

Die Idealisierungs-**Geometrie** (Teilung an Anschlüssen, Knoten-Merging,
Platten-Mittelebenen) liegt bewusst in `compas_timber` selbst
(Branch `structural_graph_plates`), nicht hier — eine Quelle der Wahrheit.

Wichtig: Das Repo hängt an einer **ungemergten compas_timber-Branch**, gepinnt auf
eine feste Revision. Installation: `uv sync --extra dev`.

## Wo es steht

**Funktioniert:** Der **Roundtrip aus Grasshopper** — Timber-Modell →
Translate → Preflight → Run (Worker-Subprozess) → RFEM 6 rechnet →
Schnittkräfte, Stab- und Knotenverformungen, Auflagerkräfte zurück → verformt
und eingefärbt auf dem Canvas. Am 2026-09-15 auf Windows gegen ein laufendes
RFEM verifiziert (Smoke-Test: 84 Balken, 404 Stäbe, 754 Objekte, ~25 s
Rechenzeit). Daneben: Balken- und Plattenpfad übersetzen; SAF-Export; ~130
automatisierte Tests offline ohne RFEM; CI installiert und testet.

**Kürzlich gemacht** (2026-09-15, Details: `packages/tekton_gh/README.md`
und `roundtrip.md`):

- **Erster Live-Roundtrip.** Vier Befunde, die offline unsichtbar waren:
  RFEM meldet gescheiterte Berechnungen nicht als Exception (jetzt:
  `has_results()` + Fehlertabelle → Klartext im Log); `get_result_table` war
  für Stäbe leer, `get_results` liefert alles; die Dlubal-API rechnet in
  **N/Nm**, der neutrale Vertrag in kN/kNm — Lasten gingen 1000× zu klein
  rein, Ergebnisse 1000× zu gross raus (ein Faktor in `conventions.py`,
  beide Richtungen); der API-Key ist auch lokal Pflicht (kommt jetzt aus
  der `.env`).
- **Kopplungen.** Der Verbinder zwischen zwei sich nicht treffenden Achsen
  ging als RFEM-Typ 24 (beidseitig gelenkig) raus — ein Pendelstab, der nur
  Normalkraft trägt; ein Balken an vier parallelen Pendelstäben ist ein
  Mechanismus. Jetzt: Gelenk nur an *einem* Ende (dem, an dem ein Balken
  endet), der Mapper leitet 21–24 aus den Releases ab. Die Joint-Policy
  entscheidet weiterhin starr/gelenkig.
- **Visualize**: verformte Systemlinien durch die 11 RFEM-Stationen pro Stab,
  Querschnitte entlang gesweept als Meshes mit Vertex-Farbe pro Station.
- **Attach Results** ruft jetzt `compas_timber_fea.results` statt einer
  eigenen Kopie: Stationswerte (inkl. Verformung) landen am Balkenparameter
  über alle Segmente in `beam.attributes["analysis"]`, mit Hüllwerten und
  Provenienz. Live: 84/84 Balken. **Results** liest dieselben Zahlen direkt
  aus dem StructuralModel (Bäume, Vorzeichen, `stale`-Prüfung).
- **OpenSees als zweites Backend** (2026-09-16): `--backend opensees` im
  Worker, im Backend-Dropdown. Sticks-Modell in 0,08 s statt 25 s. Die
  Kalibrierung gegen RFEM hat zwei Dinge aufgedeckt: RFEMs Kopplungstyp 22
  gab die Torsion frei, die der neutrale Release festhält (Mapper
  korrigiert — beide Backends treffen sich jetzt auf 5 %), und RFEMs
  Lagerkräfte sind Kräfte *auf das Lager* (neutrale Konvention: auf die
  Struktur; Dlubal-Reader dreht). Vorzeichen Station für Station gleich.
- **Rückweg Structural → Timber** (`reconstruct.py`, GH `To Timber`): Balken
  exakt aus Segmenten, Querschnitt und Orientierung, GUIDs wiederhergestellt,
  Ergebnisse dran. Joints nicht — deren Typ steht nicht im neutralen Modell.
  Damit ist das JSON allein ein vollständiges Übergabeartefakt für Balken.

**Davor** (2026-08-27, Details: `docs/review_2026-08-27.md`):

- Repo wieder installierbar (Lock war kaputt, Abhängigkeiten widersprüchlich)
- Plattenexport nach Dlubal erstmals funktionsfähig (Feldnamen aus der alten
  SOAP-API, falsche Feldtypen)
- SAF-Export war **gespiegelt** (Z-Achse) und hatte ungültige Enums — behoben
- Neutrales Modell ist jetzt **serialisierbar** (JSON) → Voraussetzung für
  Roundtrip und Übergabe an Dritte
- **Einheiten-Vertrag**: mm-Modelle ergaben stumm 200-Meter-Platten
- **Joint-Policy**: Der Fügungstyp wurde bisher komplett verworfen; jetzt
  Mapping Joint → Gelenk/Feder, überschreibbar pro Typ und Instanz, mit
  Protokoll der Annahmen; erzeugt echte RFEM-Gelenke

## Woran noch zu arbeiten ist

Ausformuliert als Arbeitspakete mit Umfang, Abhängigkeiten und Abnahme in
[work-packages.md](work-packages.md). Kurz, nach Priorität:

1. **Ausnutzung** — *die* Entwerfer-Zahl, kommt aus dem RFEM-Bemessungs-Add-on.
   Der Input existiert (`quantity="utilization"`), liefert aber 0. Nötig:
   Add-on aktivieren, dessen Ergebnistabelle über `get_results` lesen — gleiches
   Muster wie die Schnittkräfte.
2. **Joint-Policy aus Verbindungsmitteln** — heute entscheidet der Fügungstyp
   (oder eine Instanz-Regel) über starr/gelenkig. Die Regel "je nach Anzahl und
   Richtung der Schrauben biegesteif, sonst gelenkig" ist noch nicht geschrieben;
   der Haken dafür (`by_type`, `by_instance`) ist da.
3. **Platten-Ergebnisse** — Flächen werden exportiert, keine Flächentabelle
   wird gelesen. Dazu die bekannten Plattenlücken: Wand-Decke-Kopplung
   (Frame-Bug upstream), Orthotropie-Richtung, Subdivision-Logik im Paket.
4. **Stabile IDs / BackendMap** — jeder Run leert RFEM und baut neu. Was ein
   Statiker in RFEM ändert, überlebt den nächsten Run nicht. GUIDs gehen
   bereits in `id_for_export_import`; die Map fehlt.
5. **Lasten** — Lastfälle, Punkt- und Streckenlasten werden exportiert;
   Kombinationen und ein Lastkatalog (Nutzlast nach Kategorie, Schnee nach
   Zone) fehlen im Authoring.

**Bekannte Altlasten:** GUI blockiert während Export (kein Threading);
API-Key im Klartext gespeichert (GUI); Sphinx-Docs grösstenteils Platzhalter;
keine PyInstaller-Spec trotz README-Erwähnung; die Plate-Tests unter
`tests/unit/test_plate_translation.py` sind rot, weil die im `.venv`
gepinnte compas_timber-Revision `PlateStructuralElementSolver` nicht kennt —
Pin und Branch sind auseinandergelaufen.

## Offene Richtungsfrage

Mehr als das statische Modell mitliefern (Massen/LCA, Bauphysik, IFC)? Die
Architektur trägt das — sinnvoll aber erst, wenn die Statik vollständig ist.
Sonst vervielfacht man bestehende Lücken. Empfehlung: **erst vertiefen, dann
verbreitern.**

Finden gewisse Attribute upstream ihren platz? I.e. Lastfälle, Material, etc. bereits in COMPAS Timber setzbar. Workflow


## Big two to-dos

- Plate Model
- Roundtrip, attach analysis data back to timber model
- grasshopper components (my idea)

## Discussion Notes 

- detailliertere knoten bei linearen elementen
- researcher verwenden opensees / abaqus -> Modell muss da unbedingt auch funktionieren
- material editor (table)
- dokumentieren wie untersch. software alles machen machen
- wie weit tessellation von uns ?

### helpful things for building plate idealized model

- def apply_edge_extensions(self) -> None:
  - compas_timber/src/compas_timber/elements/plate_geometry.py  
  - line joint intervals
- def get_segment_range_on_polyline(segment: Line, polyline: Polyline, tol: float = 0.0) -> Optional[tuple[Point, Point]]:
  - compas_timber/src/compas_timber/geometry.py