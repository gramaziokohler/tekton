# Beispiel-Definitionen

## `tekton_smoke_test.ghx`

Der Rauchtest: zeigt die ganze Kette an einem Beispielmodell, vom Laden bis
zur exportierten Datei. Gebaut und durchgelaufen am 2026-09-10 in Rhino 8.

```text
Panel(Modellpfad) ─→ [Load Timber] ─┬─→ [Find Supports] ─┐
                                    │                    ↓
                                    └──────────→ Tekton Support ─→ Tekton Translate ─┬─→ Tekton Preflight
                                                                          ↑           ├─→ Tekton Inspect
                                                     Panel(Repo-Pfad) ────┘           └─→ Tekton Run ←── Tekton Backend
                                                                                              ↑
                                                                                          Toggle
```

Was die Definition belegt:

- **Tekton Info** findet Repo, compas_timber-Branch und Worker-venv.
- **Translate** macht aus 84 Balken 344 Knoten und 404 Stäbe, mit
  Annahmenprotokoll.
- **Support** setzt 4 Auflagerpunkte; **Preflight** meldet danach
  „Keine Befunde" (davor: „keine Auflager — Mechanismus").
- **Run** startet den Worker-Subprozess und schreibt eine SAF-Datei
  (404 Stäbe, 4 Auflager) — der Weg Rhino → Backend funktioniert.

### Vor dem ersten Öffnen

**Die beiden Pfad-Panels anpassen.** Sie enthalten absolute Pfade dieser
Maschine (Repo-Wurzel und Testmodell) — auf einem anderen Rechner zeigen sie
ins Leere. Das ist der Preis dafür, dass die Definition ohne weitere
Einrichtung läuft; die Alternative wäre ein Relativpfad, den Grasshopper nicht
kennt, weil eine `.ghx` nichts über ihren Ort weiß.

Der Repo-Pfad muss nur **einmal** gesetzt werden: Komponenten mit `repo`-Input
hinterlegen ihn für die Sitzung, alle anderen finden ihn dort wieder.

### Die zwei Script-Komponenten

`Load Timber` und `Find Supports` sind Testhilfen, keine Tekton-Komponenten:

- **Load Timber** lädt ein `TimberModel` aus JSON. COMPAS Timber bringt dafür
  keinen Baustein mit, Tekton beginnt aber dort, wo ein Modell auf dem Canvas
  liegt.
- **Find Supports** nimmt die tiefsten Balkenenden als Auflagerpunkte. In
  einem echten Entwurf setzt die der Entwerfende selbst.

### Toggle

Der Toggle an `Tekton Run` steht auf `False`, und das ist Absicht: ein Lauf
blockiert Grasshopper und baut das Backend-Modell neu auf. Er wird bewusst
gedrückt, nicht beiläufig ausgelöst.
