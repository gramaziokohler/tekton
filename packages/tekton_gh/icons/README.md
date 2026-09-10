# Icon-Quellen

Hier liegen die bearbeitbaren Originale: `<bundle>.svg` (skalierbar) und
`<bundle>_96.png` (zum Beurteilen). Was Grasshopper tatsächlich anzeigt, ist
die 24px-`icon.png` **im jeweiligen Bundle** unter `../components/<bundle>/`.

Zwei Orte, weil der Componentizer die 24px-PNG neben `code.py` und
`metadata.json` erwartet — die Bundle-Datei ist also nicht redundant, sondern
das Build-Artefakt.

## Ein Icon ändern

1. SVG hier bearbeiten.
2. Auf 24px rastern und als `../components/<bundle>/icon.png` speichern
   (die 96px-Fassung hier gleich mit aktualisieren).
3. Neu bauen und installieren — siehe [../README.md](../README.md).

`build_metadata.py` überschreibt eine vorhandene `icon.png` **nicht**; es legt
nur an, was fehlt. Die echten Icons sind also sicher.

## Stil

Aus `lorin-gh-tools/gh-icons` übernommen: Strich `#26272A` bei 1.8pt,
`stroke-linecap`/`linejoin` round, transparenter Hintergrund, ein Akzent pro
Gruppe. Die Farbzuordnung und die Motive stehen in
[../ICONS.md](../ICONS.md).

| Gruppe | Akzent |
|---|---|
| 0 \| Setup | `#a5a9ae` grau |
| 1 \| Author | `#50a9d3` hellblau |
| 2 \| Translate | `#50d3c6` türkis |
| 3 \| Run | `#d3a850` orange |
| 4 \| Results | `#8f50d3` violett |
| 5 \| IO | `#7a8288` dunkelgrau |

Ausnahme: `tekton_visualize` trägt den Ergebnis-Verlauf grün→gelb→rot, weil
genau das seine Funktion ist.
