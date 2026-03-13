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
- [ ] **Auflager 2:** Andere Auflagertypen erlauben

## Refactor
- decoupling
    - neutral structural model
    - software agnostic
    - lowest common denominator 
    - then software specific converter
- separate modules for
    - nodes, members,
    - supports,
    - loads

- multi target functionality?
    - abaqus, 
    - ansys, 
    - karamba3d, 
- save to file
    - SAF (structural analysis format),
    - IFC (structural analysis view), 
    - dlubal xml

```
src/ct_dlubal/
├── core/
│   ├── model.py          # neutral intermediary model
│   └── constants.py
├── dlubal/
│   ├── __init__.py
│   ├── client.py         # manages the connection (with AppClass...)
│   ├── mapper_nodes.py
│   ├── mapper_members.py
│   ├── mapper_supports.py
│   └── mapper_loads.py
├── importer.py           # Orchestration (call mapper, use client)
└── utils.py
```

or even:


```
src/ct_dlubal/
├── core/
│   ├── model.py            # neutral intermediary model
│   └── constants.py
├── importer/               # LIVE ACTIONS
│   ├── dlubal/             # DLUBAL SPECIFIC: API and Mappings
│   │   ├── __init__.py
│   │   ├── client.py       # manages the connection
│   │   ├── mapper_nodes.py
│   │   ├── mapper_members.py
│   │   ├── mapper_supports.py
│   │   └── mapper_loads.py
│   ├── __init__.py         # Expose dlubal_api logic
│   └── dlubal_api.py       # Orchestration (LiveImporter)
├── exporter/               # OFFLINE ACTIONS
│   ├── formats/
│   │   └── saf.py          # SAF / Excel logic
│   ├── __init__.py         # export_file(model, path, format)
│   └── base.py
├── translator.py           # compas_timber -> neutral model
└── utils.py

```

### clarify:
- do we want to target multiple fea softwares?
- first step is to model every structural relevant part -> should this be a separate neutral model?
- will ct integrate supports and loads?
    - does intermediare model make sense? overlap with fea2
    - could use compas fea2, but also maybe overkill
- flexibility for changes on both ends (ct and fea software)

### clarify:
- do we want to target multiple fea softwares?
- first step is to model every structural relevant part -> should this be a separate neutral model?
- will ct integrate supports and loads?
    - does intermediare model make sense? overlap with fea2
    - could use compas fea2, but also maybe overkill
- flexibility for changes on both ends (ct and fea software)

## GUI
- [ ] unit systems?
- [ ] scaling
- [ ] auto fetch model name
- [ ] fetch available materials?





