# tekton_gh — Grasshopper-Komponenten

*Stand: 2026-09-10 — die Kette steht durchgehend: Authoring → Translate →
Preflight → Worker → Ergebnisse zurück, offline getestet. Was noch fehlt, steht
unter „Was noch nicht echt ist"; was nur mit laufendem RFEM prüfbar ist, ist
dort benannt. Konzept: [`docs/concepts/gh-addon.md`](../../docs/concepts/gh-addon.md).*

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
reicht. In Rhino ein eigenes venv anlegen und dort die gepinnte Revision
installieren. Der Name muss zum Header jeder Komponente passen — derzeit
`# venv: tekton-test`, weil genau dieses Env auf der Maschine schon
existierte. Rhino legt bei einem unbekannten Namen stillschweigend ein
**leeres** Env an, und dann fehlt compas_timber; der Name ist also nicht
kosmetisch.

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

Schritt 3, installieren — dafuer gibt es `_componentizer/install.sh`:

```bash
bash _componentizer/install.sh    # -> UserObjects/tekton/, dann Rhino neu starten
```

Zielordner ist
`~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper (b45a29b1-…)/UserObjects/tekton/`
— der Unterordner haelt die Tekton-Komponenten von den uebrigen getrennt.
Grasshopper liest UserObjects nur beim Start, ein Neustart ist also noetig.

Der Componentizer stammt aus `lorin-gh-tools` und ist hier bewusst kopiert
statt referenziert — das Repo soll für sich baubar bleiben. Einzige Änderung:
`components/` liegt eine Ebene über dem Werkzeugordner.

## Aufbau

```text
components/<name>/        code.py + metadata.json + icon.png   (ein Bundle = eine Komponente)
src/tekton_gh/            geteilte Laufzeit: env.py, worker.py, rhino_io.py
_componentizer/           Build-Werkzeug + Metadaten-Generator
```

Die Gegenseite der Prozessgrenze liegt in `tekton_app`:
`packages/tekton_app/src/tekton_app/worker.py` — aufgerufen als
`python -m tekton_app.worker model.json --backend rfem --out ergebnis.json`.
Er lässt sich unabhängig von Grasshopper testen, und genau das tut
`tests/unit/test_worker_cli.py`.

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
| **Ausnutzung** | kommt aus dem Bemessungs-Addon von RFEM, nicht angebunden | Live-Test mit RFEM |
| **Material-Overrides** | Material ist heute nur ein Namens-String | Material-Dataclass (`discussion/materials.md`) |
| **Lagertypen** | der Translator erzeugt immer gelenkige Lager | neutrales Modell |
| **Orthotropie** | `span_direction` wird nur protokolliert | Datenmodell (`docs/handoff.md`, Punkt 3) |
| **Icons** | einfarbige Platzhalter nach Gruppe | Zeichenarbeit |

Erledigt seit dem ersten Scaffold: der **Worker-CLI** (`tekton_app.worker`)
existiert und ist getestet, und der **Ergebnis-Reader** liest inzwischen echte
Tabellen (Stabschnittgrößen, Knotenverformungen, Auflagerreaktionen). Der Weg
Rhino → Backend → Rhino ist damit durchgehend; ungetestet ist er nur gegen ein
laufendes RFEM.

## Fallstricke

**Ergebnisse veralten still.** Grasshopper hält alte Outputs fest — die Zahlen
am Canvas können ein längst geändertes Modell beschreiben. Das ist der
gefährlichste Fehlermodus dieses Workflows, und Grasshopper begünstigt ihn.
Gegenmaßnahme ist scharf: `TektonRun` stempelt den Modell-Fingerprint in jeden
Ergebnissatz, `TektonResults` vergleicht ihn gegen das angeschlossene Modell
und setzt `stale` plus eine Warnung, sobald beides auseinanderläuft.

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
