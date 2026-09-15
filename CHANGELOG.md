# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **tekton_gh**: `Tekton Visualize` draws the deformed shape — polylines through the RFEM stations, sections swept along them as vertex-coloured meshes, one colour per member; quantities `displacement | N | Vy | Vz | Mt | My | Mz | utilization`, `exaggeration` input, auto-scaled colour range. Geometry lives in `tekton_gh.visualize` (pure, tested).
- **compas_dlubal**: the result reader reads member deformations (`STATIC_ANALYSIS_MEMBERS_GLOBAL_DEFORMATIONS`) and merges them into the force stations.
- **compas_dlubal**: a failed calculation is reported with RFEM's own error text (`has_results()` + errors-and-warnings table) instead of empty results.
- **tekton_app**: the worker reads the API key from `TEKTON_API_KEY`, `DLUBAL_API_KEY`, or the repo's `.env`.
- **compas_timber_fea**: `reconstruct.structural_to_timber` rebuilds a TimberModel from a StructuralModel (beams exact: GUID, axis, section, orientation; plates when 1:1; results attached; joints not). GH component `Tekton To Timber`.
- **compas_timber_fea**: `results.samples_by_beam` projects member stations onto the physical beam axis without a timber model.
- **compas_timber_fea**: attached results carry the displacement vector per sample and in the envelope (plain tuples).
- **tekton_gh**: `Tekton Results` reworked: samples and parameters as trees with t on the beam axis (was member-local), signed envelope (was absolute), JSON record, optional TimberModel input that returns the Beam objects in order; staleness check kept.
- **tekton_gh**: `Tekton Attach Results` delegates to `compas_timber_fea.results.attach_results_to_timber` (beam-parameter samples across segments) instead of its own member-local copy, and attaches every load case unless one is chosen.
- **tekton_gh**: `Tekton Backend` accepts a file path in `api_key`; `Tekton Run` and `Tekton Visualize` reload their runtime module on every solve.
- Windows build route for the `.ghuser` components (pythonnet, no Rhino needed) documented in `packages/tekton_gh/README.md`.

### Changed
- **compas_timber_fea**: a pinned connector carries its hinge on one end only (the end where a beam terminates); both ends hinged made the connector a pendulum bar and the model a mechanism.
- **compas_dlubal**: coupling type (21–24) is derived from the member's releases instead of hard-coded to hinge-hinge.
- **compas_dlubal**: results are queried with `get_results` (raw) instead of `get_result_table` (display table, empty for members and nodes).
- **tekton_gh**: the Grasshopper worker call passes `--delete-all` for rfem/rstab, matching the documented "every run rebuilds" contract.

### Fixed
- **compas_dlubal**: unit factor at the Dlubal boundary — the neutral model is kN/kNm, the API is N/Nm. Loads were sent 1000× too small and results read 1000× too large.
- **tekton_gh**: first RFEM roundtrip from Grasshopper verified live (2026-09-15).

## [0.1.0] - 2026-04-14

### Added
- **tekton_app**: User-facing GUI application with a new 3D structural model preview and improved workflows.
- **compas_saf**: Exporter for Structural Analysis Format (SAF) files (.xlsx).
- Native support for the sections library to handle structural section additions automatically.
- Base functionality for translating structural models (nodes, members, supports).
- Early implementations of Dlubal mappers (nodes, members, supports, loads).
- Initial tests and validation for SAF export and Dlubal calculations.
- Support for object overrides, material presets, and geometric sections logic.
- Dlubal beam rotation support and Z-axis orientation handling.

### Changed
- Restructured the project into a monorepo containing decoupled packages: `compas_timber_fea`, `compas_dlubal`, `compas_saf`, and `tekton_app`.
- Moved all source packages into a dedicated `/packages/` directory for cleaner structure.
- Reworked the core logic to utilize the new structural graph from `compas_timber`.
- Incremented minimum Python version requirements.
- Refactored Dlubal mapping into isolated, modular mappers.
- Improved explicit cross-section definitions natively compatible with RFEM/RSTAB.
- Simplified top-level structures to act as a more software-agnostic bridge.

### Fixed
- Dlubal RFEM ID handling to correctly use 1-based indexing (RFEM does not support 0-based IDs).
- Addressed early RSTAB calculation issues compared to RFEM result generation.
- Corrected proper generation of dlubal objects and gRPC pushes.

