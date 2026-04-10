# ct_dlubal

## Requirements

The following software and packages are required to use `ct_dlubal`:

- **Python**: version 3.12
- **Dlubal API**: version 2.13.8
- **RFEM**: version 6.13
- **RSTAB**: version 9.13

## Installation

Stable releases can be installed from PyPI.

```bash
pip install ct_dlubal
```

To install the latest version for development, do:

```bash
git clone https://github.com/gramaziokohler/ct_dlubal.git
cd ct_dlubal
pip install -e ".[dev]"
```
## Overview & Structure

`ct_dlubal` facilitates the transfer of structural data from COMPAS-based models to Dlubal RFEM and RSTAB. It processes timber-specific geometry (beams and plates) into a neutral `StructuralModel`, which is then translated into Dlubal-compatible objects using the gRPC API. The plugin handles the mapping of nodes, members, supports, and loads, providing a GUI for model preview and synchronization.

```text
src/ct_dlubal/
├── core/
│   └── model.py          # Neutral intermediary structural model
├── dlubal/
│   ├── client.py         # gRPC connection and session management
│   ├── importer.py       # Orchestrates data flow into Dlubal
│   └── mappers/           # Specialized mappers for RFEM objects
│       ├── mapper_nodes.py
│       ├── mapper_members.py
│       ├── mapper_supports.py
│       └── mapper_loads.py
├── exporter/
│   ├── base.py           # Base classes for file exports
│   └── formats/          # File format implementations (SAF, IFC, XML)
├── gui.py                # PySide6 interface with 3D preview
├── translator.py         # COMPAS Timber to StructuralModel logic
└── utils.py              # Computational and geometry helpers
```

## Documentation

For further "getting started" instructions, a tutorial, examples, and an API reference,
please check out the online documentation here: [ct_dlubal docs](https://gramaziokohler.github.io/ct_dlubal)

## Issue Tracker

If you find a bug or if you have a problem with running the code, please file an issue on the [Issue Tracker](https://github.com/gramaziokohler/ct_dlubal/issues).



## Run GUI

```
cmd /c "set PYTHONPATH=src && C:\path\to\ct_dlubal\.venv_parallels\Scripts\python.exe -m ct_dlubal.gui"
```


## Build

```
pyinstaller --noconsole --onedir ^
  --add-data "src/ct_dlubal;ct_dlubal" ^
  --name CT-Dlubal-Sync ^
  src/ct_dlubal/gui.py
```

build from spec:

C:\path\to\ct_dlubal\.venv_parallels\Scripts\pyinstaller.exe CT-Dlubal-Sync.spec