# Tekton — Kurzübersicht

*Stand: 2026-08-28*

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
| `compas_dlubal` | Dlubal-Adapter: gRPC-Client, ein Mapper pro Objekttyp, Ergebnis-Reader (noch Scaffold). |
| `compas_saf` | SAF-Export (xlsx) — Handoff ohne Live-Verbindung. |
| `tekton_app` | GUI (PySide6) + CLI für Nutzer ohne Python. |

Die Idealisierungs-**Geometrie** (Teilung an Anschlüssen, Knoten-Merging,
Platten-Mittelebenen) liegt bewusst in `compas_timber` selbst
(Branch `structural_graph_plates`), nicht hier — eine Quelle der Wahrheit.

Wichtig: Das Repo hängt an einer **ungemergten compas_timber-Branch**, gepinnt auf
eine feste Revision. Installation: `uv sync --extra dev`.

## Wo es steht

**Funktioniert:** Balken- und Plattenpfad übersetzen; Export nach RFEM (Knoten,
Stäbe, Querschnitte, Materialien, Lager, Flächen) und nach SAF; 54 automatisierte
Tests laufen offline ohne RFEM; CI installiert und testet.

**Kürzlich gemacht** (Details: `docs/review_2026-08-27.md`):

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

Nach Priorität:

1. **Lasten** — der Importer ignoriert die Lastfälle des neutralen Modells und
   nutzt einen hartkodierten Katalog. Dasselbe Modell erzeugt so in
   verschiedenen Backends verschiedene Belastung. Lastkombinationen fehlen.
2. **Roundtrip (Ergebnisse)** — aktuell ein ehrliches Gerüst: rechnen wird
   ausgelöst, aber nichts gelesen. Nötig: Ergebnistabellen abrufen und über die
   Bauteil-GUIDs zurückmappen, pro physischem Balken aggregieren. *Das ist das
   eigentliche Versprechen an Entwerfende.*
3. **Platten** — Verbindungslinien zwischen Flächen werden nicht exportiert;
   Orthotropie-Richtung fehlt im Datenmodell (bei Holz nicht optional);
   die Subdivision-Logik liegt als nicht lauffähiges Grasshopper-Skript unter
   `tests/plate-tests/` statt im Paket.
4. **Preflight-Prüfungen** — kein Testmodell hat Auflager, und niemand warnt:
   ein lagerloses Modell geht kommentarlos in die Berechnung. Dazu:
   unverbundene Teile, fehlende Materialien.
5. **Chiralität prüfen** — die Z-Umrechnung nach RFEM ist eine Spiegelung.
   Ein Live-Test mit einem asymmetrischen Rahmen klärt, ob asymmetrische
   Strukturen seitenverkehrt ankommen. *Kleiner Aufwand, potenziell grosse
   Wirkung.*
6. **Stabile IDs / ID-Map** — Knoten-IDs stammen aus flüchtigen Graph-Indizes
   und wandern bei jeder Modelländerung. Für inkrementelle Updates und
   sitzungsübergreifende Ergebniszuordnung nötig.

**Bekannte Altlasten:** GUI blockiert während Export (kein Threading);
API-Key im Klartext gespeichert; Docs grösstenteils Platzhalter; keine
PyInstaller-Spec trotz README-Erwähnung.

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