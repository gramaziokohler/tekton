# ct_dlubal To-Do

## Done
- [x] Beam orientation from beam.frame / structural element.frame is used in translation and export.
- [x] If nodes / cross sections / materials / members are present, importer supports append or override behavior.
- [x] Nodal supports workaround via Z approximately 0 is implemented.
- [x] Material presets (GL24h, C24, etc.) are selectable via material_preset.
- [x] Connector handling supports rigid or hinged/coupling behavior.
- [x] RSTAB compatibility switch is implemented (RFEM or RSTAB target).
- [x] Basic load case and loads path implemented (self-weight load case).
- [x] GUI auto fetches and shows current model filename after load.

## Partial / Needs Follow-Up
- [ ] Check connector element validity more deeply (basic handling exists, full validation rules still missing).
- [ ] Check why get_structural_elements works incorrectly (workaround exists, root-cause fix/upstream sync pending).
- [ ] Supports "phase 2": more support types are possible via UI toggles, but automatic typed support extraction is not complete.

## Open (Core Pipeline)
- [ ] **Exzentrizitäten** verstehen/klären: Detailkonzept zu Formschluss und Systemachsenversatz erarbeiten.
- [ ] Auto-generate loads by geometry.
- [ ] Auto-generate loads according to norms.
- [ ] Get supports via timber model attributes (replace near-Z heuristic).
- [ ] support plates, line connections, line loads, and all associated elements

## Open (GUI)
- [ ] Unit systems.
- [ ] Scaling controls (mm to m or cm)
- [ ] Fetch available materials dynamically. probably unnecessary





