# Tekton

## Requirements

The following software and packages are required to use `tekton`:

- **Python**: version 3.12 (Highly recommended to avoid PyInstaller `.dll` missing errors with newer versions)
- **Dlubal API**: version 2.13.8+ (for `compas_dlubal`)
- **RFEM**: version 6.x / **RSTAB**: version 9.x

## Installation

To install the latest version for development, clone the repository. We recommend using `uv` to manage the virtual environment and enforce Python 3.12:

```bash
git clone https://github.com/gramaziokohler/tekton.git
cd tekton

# 1. Create a virtual environment specifically with Python 3.12
uv venv --python 3.12

# 2. Install base and development requirements
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt

# 3. Install local monorepo packages in editable mode
uv pip install -e ./packages/compas_timber_fea -e ./packages/compas_dlubal -e ./packages/compas_saf -e ./packages/tekton_app
```

## Overview & Structure

Tekton is a monorepo containing several decoupled packages for structural analysis and BIM synchronization within the COMPAS ecosystem. It facilitates the transfer of structural data from COMPAS-based models to Dlubal RFEM/RSTAB and neutral formats like SAF.

### Monorepo Packages

- **[compas_timber_fea](packages/compas_timber_fea)**: Agnostic bridge that translates [compas_timber](https://github.com/gramaziokohler/compas_timber) models into a neutral `StructuralModel`.
- **[compas_dlubal](packages/compas_dlubal)**: Reusable Dlubal gRPC client and importer logic.
- **[compas_saf](packages/compas_saf)**: Reusable [Structural Analysis Format (SAF)](https://www.saf.guide/) Excel exporter.
- **[tekton_app](packages/tekton_app)**: The user-facing GUI application (PySide6) and CLI tool.

```text
tekton/
├── packages/
│   ├── compas_timber_fea/    # Core translation logic (CT -> FEA)
│   ├── compas_dlubal/       # Dlubal gRPC integration
│   ├── compas_saf/          # SAF file export (xlsx)
│   └── tekton_app/          # GUI and CLI entry points
└── tests/               # Integration tests
```

## Building the Application

To build the standalone executable (`.exe`) of the GUI application, ensure your `uv` virtual environment is set up as described in the Installation instructions. 

From the root of the repository, run:

```bash
uv run pyinstaller packages/tekton_app/tekton_app.spec
```

This will create a `dist/` directory at the root of your repository containing the compiled application. *(Note: Building heavily relies on matching Python versions (3.12). If the built app fails to open, double-check that `uv` didn't default to Python 3.13.)*

## Running test.py

Provided you have completed the **Installation** steps above, your environment is ready. Run the test script using:

```bash
uv run tests/test.py
```

## Documentation

For further "getting started" instructions, a tutorial, examples, and an API reference,
please check out the online documentation here: [Tekton docs](https://gramaziokohler.github.io/tekton)

## Issue Tracker

If you find a bug or if you have a problem with running the code, please file an issue on the [Issue Tracker](https://github.com/gramaziokohler/tekton/issues).


