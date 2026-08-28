# tekton_gh — Grasshopper-Komponenten

*Stand: 2026-08-28 — Scaffold. Die Komponenten haben ihre endgültige Form
(Inputs, Outputs, Warnungen), aber ein Teil der Logik sind Platzhalter mit
`TODO(scaffold)`. Konzept: [`docs/concepts/gh-addon.md`](../../docs/concepts/gh-addon.md).*

## Warum zwei Prozesse

Rhino 8 fährt CPython **3.9**. `dlubal-api` verlangt **≥ 3.10** und zieht
grpcio, pandas und vtk mit. Der RFEM-Client kann also prinzipiell nicht in
Rhino laufen — unabhängig davon, wie wir unseren eigenen Code schreiben.

```text
┌─ Rhino 8 (CPython 3.9) ────────────────┐      ┌─ Worker (repo .venv, 3.12) ─┐
│ compas_timber (structural-Branch)      │      │ compas_dlubal → RFEM        │
│ compas_timber_fea  ← läuft hier, ✅     │ JSON │ compas_saf    → xlsx        │
│ tekton_gh (dieses Paket)               │ ───→ │                             │
│  Authoring, Translate, Inspect          │ ←─── │ rechnet, liest Ergebnisse   │
└────────────────────────────────────────┘      └─────────────────────────────┘
```

Die Prozessgrenze ist die JSON-Serialisierung des neutralen Modells. Kein
eigenes Protokoll — und jeder Lauf hinterlässt nebenbei ein diffbares Modell,
dasselbe Artefakt, das an Statiker übergeben wird.

**Verifiziert** (am 2026-08-28 in einer laufenden Rhino-8-Instanz):
`compas_timber_fea` importiert unter 3.9, `TimberToStructural.translate()`
läuft durch (Testmodell: 84 Balken → 344 Knoten, 404 Stäbe), JSON-Roundtrip
funktioniert.

## Einrichtung

**1. Rhino-venv anlegen.** Tekton braucht `compas_timber` von der Branch
`structural_graph_plates` — `compas_timber.structural` existiert nur dort. Das
offizielle COMPAS-Timber-Plugin bringt eine ältere Version mit, die *nicht*
reicht. In Rhino ein eigenes venv namens `tekton` anlegen und dort die
gepinnte Revision installieren (siehe `# venv: tekton` im Kopf jeder
Komponente).

**2. Repo-Pfad bekannt machen.** Entweder am Input `repo` der Komponenten,
oder einmalig als Umgebungsvariable:

```bash
export TEKTON_REPO="/Pfad/zum/tekton"
```

**3. Worker-venv.** Im Repo `uv sync --extra dev` — das ist das 3.12-Env, das
`TektonRun` aufruft.

**4. Prüfen.** Die Komponente **Tekton Info** auf den Canvas ziehen. Sie ist
die einzige, die auch ohne funktionierendes Setup etwas Sinnvolles ausgibt,
und nennt genau, was fehlt.

## Komponenten bauen

Schritt 1, normales Terminal-Python:

```bash
python3 _componentizer/build_metadata.py   # metadata.json + Platzhalter-Icons
```

Schritt 2 braucht .NET (`clr`), also einen Rhino-Prozess. Zwei Wege:

```bash
bash _componentizer/componetize.bash       # via RhinoCode-CLI
```

**Falls das stumm bleibt** (Exit-Code 0, aber kein `componentizer.log` und
kein `ghuser_build/`): `_componentizer/build_in_rhino.py` im Rhino-Python-Editor
öffnen und ausführen. Das ist derselbe Vorgang aus einer laufenden
Rhino-Instanz heraus. Am 2026-08-28 war die CLI auf diesem Rechner
wirkungslos — auch für den unveränderten Componentizer in `lorin-gh-tools`,
es liegt also nicht an Tekton. Der Weg über die laufende Instanz baute alle
20 Komponenten fehlerfrei.

Die fertigen `.ghuser`-Dateien nach
`~/Library/Application Support/McNeel/Rhinoceros/8.0/Grasshopper/UserObjects/`
kopieren, Rhino neu starten.

Der Componentizer stammt aus `lorin-gh-tools` und ist hier bewusst kopiert
statt referenziert — das Repo soll für sich baubar bleiben. Einzige Änderung:
`components/` liegt eine Ebene über dem Werkzeugordner.

## Aufbau

```text
components/<name>/        code.py + metadata.json + icon.png   (ein Bundle = eine Komponente)
src/tekton_gh/            geteilte Laufzeit: env.py, worker.py, rhino_io.py
_componentizer/           Build-Werkzeug + Metadaten-Generator
```

`build_metadata.py` enthält die **Komponententabelle** — Name, Kategorie,
Inputs, Outputs, Beschreibungen. Neue Komponente: dort einen Eintrag mit
frischer `uid` anhängen, Skript laufen lassen, `code.py` schreiben.

Die `uid` bestimmt die InstanceGuid und ist **stabil**: eine geänderte GUID
macht aus einer aktualisierten Komponente eine neue, und bestehende
Definitionen verlieren ihre Verkabelung. Nur anhängen, nie neu vergeben.

## Die Komponenten

**0 | Setup** — `Tekton Info`: Diagnose. Erste Anlaufstelle bei Problemen.

**1 | Author** — was heute nur in Python ging: `Material`, `Support`,
`Load Case`, `Point Load`, `Member Load`, `Load Combination`, `Joint Policy`,
`Plate Policy`.

**2 | Translate** — `Translate` (TimberModel → StructuralModel, mit
Annahmenprotokoll), `Apply Loads` (Lasten aufs übersetzte Modell),
`Preflight` (Auflager? zusammenhängend? plausibel?).

**3 | Run** — `Backend` (Auswahl + Verbindung), `Run` (push, rechnen,
Ergebnisse zurück — **nur per Button**).

**4 | Results** — `Results` (Hüllwerte je Balken), `Attach Results` (zurück
aufs Timber-Modell), `Visualize` (einfärben), `Inspect` (Ersatzsystem
anschauen).

**5 | IO** — `Save Model` / `Load Model` (JSON; zugleich das Übergabeformat).

## Typischer Ablauf

```text
TimberModel ─→ Support ─→ Translate ─→ Preflight ─→ Run ─→ Results ─→ Visualize
                 ↑            ↑                      ↑
            Load Case    Joint Policy            Backend
                 ↓
          Point/Member Load ─→ Apply Loads
```

## Was noch nicht echt ist

Das Scaffold hat die richtige Form, aber diese Stellen sind Platzhalter —
jeweils mit `TODO(scaffold)` im Code markiert:

| Was | Warum | Blockiert durch |
|---|---|---|
| **Ergebnisse** | `DlubalResultReader` löst die Berechnung aus, liest aber nichts | Roundtrip (`discussion/roundtrip.md`) |
| **Worker-CLI** | `tekton_app.worker` existiert noch nicht; `TektonRun` schlägt bis dahin fehl | kleine Arbeit, gehört nach `tekton_app` |
| **Material-Overrides** | Material ist heute nur ein Namens-String | Material-Dataclass (`discussion/materials.md`) |
| **Lasten in RFEM** | Der Importer nutzt einen fest verdrahteten Katalog | Priorität 1 in `docs/handoff.md` |
| **Ausnutzung** | kommt aus dem Bemessungs-Addon, ungetestet | Live-Test mit RFEM |
| **Lagertypen** | der Translator erzeugt immer gelenkige Lager | neutrales Modell |
| **Orthotropie** | `span_direction` wird nur protokolliert | Datenmodell (`docs/handoff.md`, Punkt 3) |
| **Icons** | einfarbige Platzhalter nach Gruppe | Zeichenarbeit |

## Fallstricke

**Ergebnisse veralten still.** Grasshopper hält alte Outputs fest — die Zahlen
am Canvas können ein längst geändertes Modell beschreiben. Das ist der
gefährlichste Fehlermodus dieses Workflows. `worker.model_fingerprint()` und
der `stale`-Ausgang von `TektonResults` sind dafür da; sobald der Fingerprint
beim Rechnen mitgeschrieben wird, greift die Prüfung.

**Nie automatisch rechnen.** `TektonRun` blockiert Grasshopper, solange
gerechnet wird, und jeder Lauf baut das Backend-Modell neu auf. Darum
Button-getriggert, mit Zwischenspeicher, damit ein Canvas-Update die
Ergebnisse nicht wegwirft.

**Einheiten.** Rhino-Dokumente sind typisch mm, das neutrale Modell rechnet in
Metern. `TektonTranslate` liest die Dokumenteinheit selbst aus; wer sie
überschreibt, sollte wissen warum. Ein falscher Wert erzeugt lautlos ein
200-Meter-Bauteil.

**API-Key.** Nicht in den Canvas — die `.gh`-Datei wandert weiter. Stattdessen
`TEKTON_API_KEY` in der Umgebung.

**compas_timber-Version.** Der häufigste Setup-Fehler. Wenn `Tekton Info`
sagt, `compas_timber.structural` fehle, ist das falsche `compas_timber` im
Zugriff — meist das des offiziellen Plugins.
