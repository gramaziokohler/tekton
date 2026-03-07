- get beam orientation from beam.frame / structural element.frame
- if nodes / crossections / materials / members are present then give choice to append or override.
- check connector element for validity
- check why get_structural_elements is working incorrectly

## Next Steps (Core Pipeline)
- [x] **Auflager (Nodal Supports):** Zunächst Workaround via `Z ≈ 0` für Fundament-Knoten, später attributbasiert aus `compas_timber`.
- [x] **Materialien:** Festigkeitsklassen (GL24h, C24 etc.) über `material_preset` auswählbar gemacht.
- [x] **Stabgelenke / Connectors:** Connectors optional als `rigid` oder parametrisch mit `Stabendgelenken` (Freigabe von Momenten etc.) ausführen lassen.
- [ ] **Exzentrizitäten verstehen/klären:** Detailkonzept zu Formschluss und Systemachsenversatz erarbeiten.
- [X] **RSTAB-Kompatibilität:** API-Blockade beim Wechsel auf RSTAB beheben.
- [x] **Lastfälle & Lasten:** Elementare Lastfälle Eigengewicht (LF1) inkl. Berechnungseinstellungen implementiert.

-auto fetch model name
-fetch available materials?
....