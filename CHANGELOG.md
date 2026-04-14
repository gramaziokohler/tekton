# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

