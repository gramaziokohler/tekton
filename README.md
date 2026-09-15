# Tekton

Tekton carries a [COMPAS Timber](https://github.com/gramaziokohler/compas_timber)
design into structural analysis and brings the numbers back onto the beams.
It translates the timber model into a neutral `StructuralModel`, pushes that
to Dlubal RFEM/RSTAB or writes it as a [SAF](https://www.saf.guide/)
spreadsheet, and reads the results back so they land on the design model as
attributes. It is driven from Grasshopper, a desktop app, a command line, or
plain Python.

## System map

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/_images/architecture/tekton-system-map-dark.svg">
  <img alt="Tekton system map. COMPAS Timber authors the TimberModel and builds the StructuralGraph that idealises the geometry. Tekton reads that graph from Grasshopper, the desktop app or a script, always through the same translator, and hands the neutral StructuralModel to a backend adapter. Results hop back across the top until they land on the beams. Only Grasshopper's Run button takes the detour through a JSON file and a worker subprocess." src="docs/_images/architecture/tekton-system-map.svg">
</picture>

Read it left to right; the round trip runs right to left along the top. Click
the image to open it at full size. The remaining diagrams and the notes behind
them are in [`docs/architecture.html`](docs/architecture.html).

## Packages

The repository is a `uv` workspace holding five packages under `packages/`.

| Package | Role | Runs where |
| --- | --- | --- |
| [`compas_timber_fea`](packages/compas_timber_fea) | The neutral layer: `TimberToStructural` translator, joint and plate policies, units, preflight, serialization, results back onto beams | anywhere, including Rhino's Python 3.9 |
| [`compas_dlubal`](packages/compas_dlubal) | RFEM/RSTAB adapter: gRPC client, object mappers, result reader | Python ≥ 3.10 (the `dlubal-api` floor) |
| [`compas_saf`](packages/compas_saf) | SAF `.xlsx` exporter | Python ≥ 3.10 |
| [`tekton_app`](packages/tekton_app) | Desktop GUI (PySide6), the `tekton` CLI, and the worker subprocess Grasshopper calls | Python ≥ 3.10 |
| [`tekton_gh`](packages/tekton_gh) | 23 Grasshopper components: author loads and supports, translate, run, results, visualise, save and load | Rhino 8 |

The rule that keeps them apart: if a value depends on which software you are
talking to, it lives in an adapter. If it depends on engineering judgement, it
lives in the neutral layer as an explicit, reported policy.

```text
tekton/
├── packages/
│   ├── compas_timber_fea/   # neutral model, translator, policies, results
│   ├── compas_dlubal/       # RFEM/RSTAB via gRPC
│   ├── compas_saf/          # SAF export (xlsx)
│   ├── tekton_app/          # GUI, `tekton` CLI, worker subprocess
│   └── tekton_gh/           # Grasshopper components + componentizer
├── docs/                    # Sphinx sources, architecture.html, diagrams
└── tests/
    ├── unit/                # automated, offline (run in CI)
    └── *.py                 # manual scripts against a live RFEM
```

## Requirements

- **Python ≥ 3.10** for everything outside Rhino. The workspace pins 3.12 via
  `.python-version`; `uv` installs it for you.
- **Rhino 8** for the Grasshopper components. Rhino ships CPython 3.9, which is
  why the RFEM client runs in a separate worker process (see the map).
- **Dlubal API 2.13.8** (pinned) with **RFEM 6.13** or **RSTAB 9.13**, only if
  you push to Dlubal. SAF export needs neither.
- **`compas_timber` from the `structural_graph_plates` branch**, pinned to a
  revision in `pyproject.toml`. The released COMPAS Timber does not carry
  `compas_timber.structural`, which Tekton reads.

## Installation

```bash
git clone https://github.com/gramaziokohler/tekton.git
cd tekton
uv sync --extra dev
```

Run anything through `uv run`, which uses that environment:

```bash
uv run pytest          # automated tests, no RFEM needed
uv run ruff check .    # lint
uv run tekton --help   # CLI
```

For the Grasshopper components, follow
[`packages/tekton_gh/README.md`](packages/tekton_gh/README.md): it covers the
dedicated Rhino venv with the branch build, building the `.ghuser` files, and
the `Tekton Info` component that tells you what is missing.

### API key

Anything that talks to RFEM/RSTAB needs a Dlubal API key. Put it in a `.env`
file at the repository root (copy `.env.example`). `.env` is gitignored; do
not commit it. The worker also accepts `TEKTON_API_KEY` in the environment,
and the GUI takes the key in its settings.

## Usage

### Grasshopper

Build the timber model with the COMPAS Timber components as usual. Tekton
starts where a `TimberModel` sits on the canvas: mark supports, pick a grade,
author load cases, then `Tekton Translate`, `Tekton Preflight`, and `Tekton
Run`. Run is button-gated because it pushes to RFEM, calculates, and reads
back, which takes seconds to minutes. `Tekton Results` and `Tekton Visualize`
put the numbers on the beams; `Tekton Results` also warns when the results are
older than the model they are wired to.

### Desktop

```bash
uv run tekton --gui
```

Drop a `timber_model.json`, choose SAF or a live push, and go. This path needs
no Rhino.

### Command line

```bash
uv run tekton timber_model.json --output model.xlsx        # SAF
uv run tekton timber_model.json --dlubal --app rfem        # push to RFEM
```

The worker Grasshopper shells out to is also a CLI. It takes a serialized
`StructuralModel`, not a timber model:

```bash
uv run python -m tekton_app.worker model.json --backend rfem --out model.result.json
```

### Python

```python
from compas.data import json_load
from compas_timber_fea.translator import TimberToStructural
from compas_timber_fea.results import attach_results_to_timber
from compas_dlubal.dlubal.importer import DlubalImporter
from compas_dlubal.dlubal.result_reader import DlubalResultReader

timber_model = json_load("timber_model.json")

translator = TimberToStructural(connector_mode="rigid", material_name="C24")
structural_model = translator.translate(timber_model)
for line in translator.report:      # every assumption the translator made
    print(line)

DlubalImporter(app_type="rfem", delete_all=True).run(structural_model)
structural_model.results = DlubalResultReader(app_type="rfem").read(
    load_cases=[1], calculate=True, structural_model=structural_model
)

attach_results_to_timber(structural_model, timber_model)
# beam.attributes["analysis"] now holds samples, envelope and provenance
```

No file is written on this path: the `StructuralModel` object goes straight
into the adapter. Serialization exists for the Grasshopper split, and for
handing a model to an engineer.

## Status

As of 2026-09-15 the round trip is real: the smoke test goes from Grasshopper
to RFEM and back, and every beam gets its forces, deformations, envelope and
provenance. Still open, in rough order of value:

- **Utilisation.** The quantity exists on `Tekton Visualize` and returns 0.
  It needs RFEM's timber design add-on.
- **Material overrides.** One grade for the whole model.
- **Support types.** Pinned unless authored via `Tekton Support Nodes`.
- **Plate results.** Surfaces are pushed; no surface result table is read.
- **The engineer's edits in RFEM.** Every run rebuilds the model, so they do
  not survive. Needs a persistent identifier map.

The full table lives in
[`packages/tekton_gh/README.md`](packages/tekton_gh/README.md#what-is-not-real-yet).

## Tests

The automated suite runs offline. It builds real Dlubal protobuf messages and
SAF spreadsheets without connecting to RFEM:

```bash
uv run pytest
```

The scripts directly under `tests/` are manual: they need a running
RFEM/RSTAB instance and the API key, and they report by printing rather than
asserting. Run them individually, for example `uv run tests/test-roundtrip.py`.

## Development notes

### Working against a local compas_timber checkout

To develop against a local clone instead of the pinned revision, add a source
override to the root `pyproject.toml`:

```toml
[tool.uv.sources]
compas_timber = { path = "../compas_timber", editable = true }
```

Then run `uv sync` again. Revert the override before committing.

### iCloud Drive

If the repository lives in iCloud Drive, the workspace packages can suddenly
become unimportable (`ModuleNotFoundError: compas_timber_fea`). iCloud sets
the macOS *hidden* flag on synced files, and Python ≥ 3.12 skips hidden `.pth`
files in site-packages, which is how editable installs are wired up.

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
```

Durable fix: keep the venv outside iCloud, for example
`export UV_PROJECT_ENVIRONMENT=~/.venvs/tekton` before `uv sync`.

### Building a standalone executable

Building one requires a PyInstaller spec file, which is not part of the
repository at present.

## Documentation

Online documentation, with a tutorial and an API reference:
[gramaziokohler.github.io/tekton](https://gramaziokohler.github.io/tekton).

## Issue tracker

Found a bug or stuck? File an issue on the
[issue tracker](https://github.com/gramaziokohler/tekton/issues).
