# Icon-Briefing — Tekton-Komponenten

Vorlage für die Icon-Gestaltung der 20 Grasshopper-Komponenten. Derzeit
laufen alle mit einfarbigen Platzhaltern (eine Fläche pro Gruppe).

## Hausstil (aus `lorin-gh-tools/gh-icons`)

```
Canvas        24 × 24, viewBox "0 0 24 24", Hintergrund transparent
Strich        #26272A, stroke-width 1.8, linecap/linejoin round, fill none
Akzent        eine Farbe pro Kategorie, sparsam — trägt die Aussage
Knoten        Kreise r=1.5 (normal) / r=1.8–2.1 (betont), gefüllt, stroke none
Lieferung     <name>.svg + <name>_24.png + <name>_96.png
```

Referenz-SVG (`mesh-topology.svg`) als Muster für Aufbau und Strichführung:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"
     fill="none" stroke="#26272A" stroke-width="1.8"
     stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 13 L5 9 M12 13 L20 7"/>
    <circle cx="5" cy="9" r="1.5" fill="#26272A" stroke="none"/>
    <path d="M12 13 L13 8.5" stroke="#98d350"/>
</svg>
```

**Bestehende Akzentfarben** (nicht wiederverwenden, damit Tekton unterscheidbar
bleibt): `#505fd3` Basic Geometry, `#d35052` Architecture/Terrain, `#98d350`
Analysis, `#c650d3` Diverse, `#a5a9ae` General Tools.

## Farbvorschlag für Tekton

Tekton ist eine eigene Ribbon-Kategorie mit sechs Gruppen. Vorschlag, im
bestehenden System (`…d3`-Sättigung, 50/100-Wertigkeit) und in einer Ecke des
Farbkreises, die noch frei ist — Cyan/Türkis:

| Gruppe | Akzent | Begründung |
|---|---|---|
| 0 \| Setup | `#a5a9ae` grau | Diagnose, keine Fachaussage — wie General Tools |
| 1 \| Author | `#50a9d3` hellblau | Eingaben, die der Entwerfende setzt |
| 2 \| Translate | `#50d3c6` türkis | die Übersetzung selbst, das Herzstück |
| 3 \| Run | `#d3a850` orange | Aktion mit Außenwirkung, Vorsicht geboten |
| 4 \| Results | `#8f50d3` violett | Rückfluss aus der Berechnung |
| 5 \| IO | `#7a8288` dunkelgrau | Datei rein/raus, dienend |

Alternative, falls es einfacher sein soll: **eine** Tekton-Farbe (`#50d3c6`)
für alle, und die Gruppen nur über das Motiv unterscheiden.

## Durchgehende Bildsprache

Tekton übersetzt **physische Bauteile** in ein **mechanisches Ersatzsystem**.
Diese Dualität sollte sich durchziehen:

- **Bauteil** = Rechteck/Balken mit Breite (dicker Umriss)
- **Ersatzsystem** = dünne Systemlinie mit Knotenpunkten
- **Knoten** = gefüllter Kreis
- **Auflager** = Dreieck oder Schraffur unter einem Knoten
- **Gelenk** = kleiner offener Kreis im Stab (Standard-Statiksymbol)

Wo möglich Statiksymbole verwenden, wie sie Ingenieure kennen — das Publikum
liest sie ohne Erklärung.

---

# Die 20 Komponenten

## 0 | Setup — grau `#a5a9ae`

### Tekton Info (`TInfo`)
Diagnose der Umgebung: Python-Version, compas_timber-Version, ist das Repo
gefunden, gibt es das Worker-venv. Erste Anlaufstelle, wenn etwas rot ist.
*Motiv:* Häkchen/Kreuz-Liste oder ein „i" im Kreis; alternativ Stethoskop-Idee
— etwas, das „Zustand prüfen" sagt, nicht „Information anzeigen".

---

## 1 | Author — hellblau `#50a9d3`

Was der Entwerfende dem Modell an Ingenieurwissen mitgibt. Gemeinsame Klammer:
**etwas wird an ein Bauteil geheftet.**

### Tekton Material (`TMat`)
Werkstoff wählen (C24, GL24h …). Heute ein Name, den RFEM gegen seine
Bibliothek auflöst.
*Motiv:* Balkenquerschnitt mit Holzmaserung/Jahresringen; Akzent auf der
Maserung.

### Tekton Support (`TSup`)
Auflagerpunkte auf Balken markieren.
*Motiv:* Balken waagerecht, darunter das klassische Auflager-Dreieck in Akzent.
Das eindeutigste Symbol im ganzen Set — sollte sofort lesbar sein.

### Tekton Load Case (`TCase`)
Lastfall definieren (Eigengewicht, Nutzlast, Schnee, Wind). Ein Container, auf
den sich Lasten beziehen.
*Motiv:* Mehrere gestapelte Ebenen/Karten, eine davon in Akzent
hervorgehoben — „einer von mehreren Fällen".

### Tekton Point Load (`TPLoad`)
Einzellast an einem Punkt, Kraft in kN.
*Motiv:* Ein einzelner dicker Abwärtspfeil auf einen Punkt, Pfeil in Akzent.

### Tekton Member Load (`TMLoad`)
Streckenlast auf Balken, kN/m.
*Motiv:* Reihe gleich langer Abwärtspfeile über einem Balken, mit der
verbindenden Oberlinie (Standard-Darstellung einer Gleichlast).

### Tekton Load Combination (`TComb`)
Lastfälle mit Teilsicherheitsbeiwerten kombinieren.
*Motiv:* Zwei/drei Pfeile, die in einen zusammenlaufen; oder Σ-Geste. Der
Unterschied zu Load Case muss klar sein: hier **verrechnen**, dort **benennen**.

### Tekton Joint Policy (`TPolicy`)
Regel, wie eine Holzverbindung mechanisch idealisiert wird: gelenkig, steif
oder Feder. Eine Ingenieurentscheidung, keine Geometrie.
*Motiv:* Zwei sich treffende Stäbe, am Treffpunkt der offene Kreis des
Gelenksymbols in Akzent. Idealerweise sichtbar, dass es eine *Wahl* ist —
etwa zwei Varianten nebeneinander.

### Tekton Plate Policy (`TPlatePol`)
Wie Plattenränder gekoppelt werden (gelenkig/durchlaufend), plus die
Tragrichtung. Letztere ist nicht Kür: Plattenwerkstoffe sind orthotrop, und
RFEMs m_x folgt den Flächenachsen — ohne festgelegte Richtung sind die
Momente nicht interpretierbar.
*Motiv:* Zwei aneinanderstoßende Platten in Draufsicht, die Fuge betont, plus
Richtungspfeil für die Spannrichtung. Der Pfeil ist die eigentliche Aussage —
gern in Akzent, die Fuge dunkel.

---

## 2 | Translate — türkis `#50d3c6`

Der Kern: aus Bauteilen wird ein Ersatzsystem.

### Tekton Translate (`TTrans`)
TimberModel → neutrales Statikmodell. Erzeugt Systemlinien, Knoten,
Querschnitte, Gelenke, Lager, plus Annahmenprotokoll.
*Motiv:* **Das Schlüsselbild des Sets.** Links ein Balken mit Breite (dicker
Umriss), rechts dieselbe Geometrie als dünne Systemlinie mit Knotenpunkten,
dazwischen ein Pfeil. Idealerweise als eine Figur, die auf halber Strecke vom
Bauteil zur Linie wechselt.

### Tekton Apply Loads (`TApply`)
Setzt die authorierten Lasten auf das übersetzte Modell (Punkt → Knoten,
Bauteil-GUID → alle daraus entstandenen Stäbe).
*Motiv:* Systemlinie mit Knoten, Lastpfeile rasten darauf ein; Akzent auf den
Pfeilen. Unterschied zu Point/Member Load: dort wird die Last *definiert*,
hier *zugeordnet*.

### Tekton Preflight (`TCheck`)
Prüft vor dem Rechnen: Auflager da? Modell zusammenhängend? Verweise gültig?
Verhindert, dass ein schwebendes System kommentarlos gerechnet wird.
*Motiv:* Systemlinie mit Warndreieck oder Prüfhäkchen; Akzent auf dem Befund.
Die Aussage ist „Kontrolle vor dem Start", nicht „Fehler".

---

## 3 | Run — orange `#d3a850`

Aktion mit Außenwirkung — die Farbe soll zum Innehalten bewegen.

### Tekton Backend (`TBackend`)
Backend wählen (RFEM/RSTAB/SAF) und Verbindungsdaten bündeln.
*Motiv:* Stecker/Port oder ein Umschalter mit zwei/drei Zielen. Etwas, das
„Ziel auswählen und verbinden" sagt.

### Tekton Run (`TRun`)
Modell ans Backend, rechnen, Ergebnisse zurück. Läuft in einem eigenen Prozess.
**Nur per Button** — der Lauf blockiert Grasshopper und baut das Backend-Modell
neu auf.
*Motiv:* Play-Dreieck, kombiniert mit dem Kreislauf-Pfeil (hin und zurück).
Muss als „das ist der Auslöser" erkennbar sein.

---

## 4 | Results — violett `#8f50d3`

Was aus der Berechnung zurückkommt.

### Tekton Results (`TRes`)
Ergebnisse je physischem Balken: Hüllwerte und Stützstellen entlang der Achse.
Warnt, wenn die Zahlen zu einem älteren Modellstand gehören.
*Motiv:* Balken mit darüberliegender Momentenlinie/Kurve; Akzent auf dem
Extremwert. Statik-Diagrammsprache.

### Tekton Attach Results (`TAttach`)
Schreibt die Ergebnisse zurück aufs Timber-Modell, mit Herkunftsangabe.
*Motiv:* Pfeil, der von einer Kurve/Zahl zurück auf einen Balken zeigt — die
Richtung „zurück aufs Bauteil" ist die Aussage.

### Tekton Visualize (`TViz`)
Färbt Bauteile nach einem Ergebniswert ein, mit Legende. Über der Obergrenze
hart rot.
*Motiv:* Balken in Farbverlauf (grün→gelb→rot) — hier darf ausnahmsweise mehr
Farbe als sonst ins Icon, weil genau das die Funktion ist.

### Tekton Inspect (`TInspect`)
Zeigt das Ersatzsystem selbst: Systemlinien, Knoten, Lagersymbole,
Gelenkmarker. Zum Prüfen der Idealisierung vor dem Rechnen.
*Motiv:* Lupe über einem Systemlinien-Fachwerk mit sichtbaren Knoten. Der
Unterschied zu Results: hier das **System**, dort die **Zahlen**.

---

## 5 | IO — dunkelgrau `#7a8288`

### Tekton Save Model (`TSave`)
Schreibt das neutrale Modell als JSON — zugleich das Übergabeformat an
Statiker, samt Annahmenprotokoll.
*Motiv:* Systemlinien-Figur, die in ein Dokument/eine Datei fließt; Pfeil nach
unten/hinein.

### Tekton Load Model (`TLoad`)
Liest ein gespeichertes Modell samt Ergebnissen zurück auf den Canvas.
*Motiv:* Spiegelbild zu Save — Pfeil aus dem Dokument heraus. Die beiden
sollten als Paar erkennbar sein.

---

## Hinweise zur Umsetzung

- **24px ist die echte Größe.** Alles muss dort lesbar bleiben: höchstens
  zwei, drei Bildelemente, keine dünnen Details, keine Schrift.
- **Paare sichtbar machen:** Save/Load, Point Load/Member Load, Joint
  Policy/Plate Policy, Results/Inspect. Gleiche Grundfigur, ein Element
  gespiegelt oder getauscht.
- **Der Akzent trägt die Aussage.** Im Referenz-SVG ist genau das Neue farbig,
  der Kontext bleibt dunkel. So bleibt die Bedeutung auch in Graustufen lesbar.
- **Nicht jedes Icon braucht ein Novum.** Wo ein etabliertes Statiksymbol
  existiert (Auflager, Gelenk, Gleichlast), ist es die richtige Wahl.

## Dateien ablegen

Fertige Icons hierhin, dann neu bauen:

```
components/<bundle>/icon.png     # 24px, ersetzt den Platzhalter
```

Bundle-Namen: `tekton_info`, `tekton_material`, `tekton_support`,
`tekton_load_case`, `tekton_point_load`, `tekton_member_load`,
`tekton_combination`, `tekton_joint_policy`, `tekton_plate_policy`,
`tekton_translate`, `tekton_apply_loads`, `tekton_preflight`,
`tekton_backend`, `tekton_run`, `tekton_results`, `tekton_attach_results`,
`tekton_visualize`, `tekton_inspect`, `tekton_save_model`,
`tekton_load_model`.

Danach:

```bash
python3 _componentizer/build_metadata.py   # laesst vorhandene icon.png in Ruhe
# Componentizer laufen lassen (siehe README), dann:
bash _componentizer/install.sh
```

`build_metadata.py` überschreibt eine vorhandene `icon.png` **nicht** — es legt
nur an, was fehlt. Echte Icons sind also sicher.
