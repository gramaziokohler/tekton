- get beam orientation from beam.frame / structural element.frame
- if nodes / crossections / materials / members are present then give choice to append or override.
- check connector element for validity
- check why get_structural_elements is working incorrectly

## Next Steps (Core Pipeline)
- [ ] **Auflager (Nodal Supports):** Zunächst Workaround via `Z ≈ 0` für Fundament-Knoten, später attributbasiert aus `compas_timber`.
- [ ] **Stabgelenke / Connectors:** Connectors optional als `rigid` oder parametrisch mit `Stabendgelenken` (Freigabe von Momenten etc.) ausführen lassen.
- [ ] **Exzentrizitäten verstehen/klären:** Detailkonzept zu Formschluss und Systemachsenversatz erarbeiten.
- [ ] **Materialien:** Dropdown / Auswahlmöglichkeit gängiger Holz-Festigkeitsklassen (wie GL24h, C24 etc.) für den gesamten Export, da COMPAS Timber keine spezifischen Materialdaten mitliefert.
- [ ] **Lastfälle & Lasten:** (Später) Elementare Lastfälle (z.B. Eigengewicht) und Lasten implementieren.
- [ ] **RSTAB-Kompatibilität:** API-Blockade beim Wechsel auf RSTAB beheben.
