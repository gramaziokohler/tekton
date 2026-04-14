# Tekton

## Requirements

The following software and packages are required to use `tekton`:

- **Python**: version 3.12+
- **Dlubal API**: version 2.13.8+ (for `compas_dlubal`)
- **RFEM**: version 6.x / **RSTAB**: version 9.x

## Installation

To install the latest version for development, clone the repository and install the packages in editable mode:

```bash
git clone https://github.com/gramaziokohler/tekton.git
cd tekton
pip install -e ./packages/compas_timber_fea -e ./packages/compas_dlubal -e ./packages/compas_saf -e ./packages/tekton_app
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

If you want to build the standalone executable (`.exe`) of the GUI application, make sure you have the development requirements installed (`pyinstaller` is required):

```bash
uv pip install -r requirements-dev.txt
```

Then, from the root of the repository, run:

```bash
uv run pyinstaller packages/tekton_app/tekton_app.spec
```

This will create a `dist/` directory at the root of your repository containing the compiled application.

## Documentation

For further "getting started" instructions, a tutorial, examples, and an API reference,
please check out the online documentation here: [Tekton docs](https://gramaziokohler.github.io/tekton)

## Issue Tracker

If you find a bug or if you have a problem with running the code, please file an issue on the [Issue Tracker](https://github.com/gramaziokohler/tekton/issues).


