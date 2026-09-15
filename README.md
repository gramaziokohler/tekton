# Tekton

## Requirements

The following software and packages are required to use `tekton`:

- **Python**: version 3.12 (Highly recommended to avoid PyInstaller `.dll` missing errors with newer versions)
- **Dlubal API**: version 2.13.8+ (for `compas_dlubal`)
- **RFEM**: version 6.13 / **RSTAB**: version 9.13

## Installation

The repository is a `uv` workspace, so one command installs the interpreter
(pinned to 3.12 via `.python-version`), all four packages, and the dev tools:

```bash
git clone https://github.com/gramaziokohler/tekton.git
cd tekton

uv sync --extra dev
```

Run anything through `uv run`, which uses that environment:

```bash
uv run pytest          # automated tests (no RFEM needed)
uv run ruff check .    # lint
uv run tekton --help   # CLI
```

### Working against a local compas_timber checkout

Tekton depends on the `compas_timber.structural` API from the
`structural_graph_plates` branch, pinned to a fixed revision in
`pyproject.toml` and `requirements.txt`. To develop against a local clone
instead, add a source override to the root `pyproject.toml`:

```toml
[tool.uv.sources]
compas_timber = { path = "../compas_timber", editable = true }
```

Then run `uv sync` again. Revert the override before committing.

> **Note (iCloud Drive):** if the repository lives in iCloud Drive, the
> workspace packages can suddenly become unimportable
> (`ModuleNotFoundError: compas_timber_fea`). Cause: iCloud asynchronously
> sets the macOS *hidden* flag on synced files, and Python ≥3.12 skips hidden
> `.pth` files in site-packages — which is exactly how editable installs are
> wired up. Quick fix:
>
> ```bash
> chflags nohidden .venv/lib/python3.12/site-packages/*.pth
> ```
>
> Durable fix: keep the venv outside iCloud, e.g.
> `export UV_PROJECT_ENVIRONMENT=~/.venvs/tekton` before `uv sync`.

## Overview & Structure

Tekton is a monorepo containing several decoupled packages for structural analysis and BIM synchronization within the COMPAS ecosystem. It facilitates the transfer of structural data from COMPAS-based models to Dlubal RFEM/RSTAB and neutral formats like SAF.

### System map

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/_images/architecture/tekton-system-map-dark.svg">
  <img alt="Tekton system map. COMPAS Timber authors the TimberModel and builds the StructuralGraph that idealises the geometry. Tekton reads that graph from Grasshopper, the desktop app or a script, always through the same translator, and hands the neutral StructuralModel to a backend adapter. Results hop back across the top until they land on the beams. Only Grasshopper's Run button takes the detour through a JSON file and a worker subprocess." src="docs/_images/architecture/tekton-system-map.svg">
</picture>

Read it left to right; the round trip runs right to left along the top. Click the image to open it at full size. The remaining diagrams and the notes behind them are in [`docs/architecture.html`](docs/architecture.html).

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
└── tests/
    ├── unit/            # Automated tests (run in CI, no RFEM required)
    └── *.py             # Manual scripts requiring a live RFEM instance
```

## Tests

The automated suite runs offline — it builds real Dlubal protobuf messages and
SAF spreadsheets without connecting to RFEM:

```bash
uv run pytest
```

The scripts directly under `tests/` are manual: they need a running
RFEM/RSTAB instance and a `DLUBAL_API_KEY` (see `.env.example`), and they
report by printing rather than asserting. Run them individually, e.g.
`uv run tests/test-roundtrip.py`.

## Building the Application

Building the standalone executable requires a PyInstaller spec file, which is
not currently part of the repository.

## Documentation

For further "getting started" instructions, a tutorial, examples, and an API reference,
please check out the online documentation here: [Tekton docs](https://gramaziokohler.github.io/tekton)

## Issue Tracker

If you find a bug or if you have a problem with running the code, please file an issue on the [Issue Tracker](https://github.com/gramaziokohler/tekton/issues).


