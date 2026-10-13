# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **tekton_gh**: new `Tekton Area Load` (TALoad) - kN/m2 on a beam grid without plates. Regions are closed curves tested in plan (even-odd, so outline + inner curve is the ring between); `Tekton Apply Loads` finds the fields of the level after translating and hands each field's load to its members (45-degree rule for rectangles, centroid rule otherwise), total conserved. Logic in `compas_timber_fea.core.load_distribution` (pure, tested); on the HIL roof it reproduces the hand-written load script member by member. A wired `regions` input that delivers no curve (a referenced curve gone from the Rhino document) gives a warning and no load, never the whole level.
- **tekton_gh**: `Tekton Display` gets `badges` - the text dots (support types, load values) are off unless switched on.
- **compas_dlubal**: WP1 - utilisation from RFEM's timber design add-on. `DlubalImporter(design=True)` sets the add-on up after the push (`design_setup.py`: add-on + EN 1995, service class, ULS configuration with stability off, combination wizard generating *load* combinations, ULS design situation); `DlubalResultReader.read(design=True)` reads `TIMBER_DESIGN_MEMBERS_DESIGN_RATIOS_BY_LOCATION` into `metadata["utilization"]` / `governing_check` / `check_type` per station and records the combinations it was computed for. The one thing the API cannot set - the wizard's standard group "EN 1990 | Basis + Holz" - is detected and reported with the GUI step. Recorded table as `tests/unit/fixtures/sticks_rfem_timber_design.json`.
- **compas_timber_fea**: `DesignAssumptions.size_factor` - k_h is now opt-in (off like RFEM's default; omitting it is the safe side). Cross-check `tests/unit/test_rfem_timber_design.py`: our EC5 checks reproduce RFEM's ratios on the sticks model to 1e-5 (bending + compression) and 2e-3 (bending + tension).
- **tekton_gh**: `Tekton Backend` gets `design` (rfem only); `Tekton Results` quantity `utilization` works and names the design loading; `Tekton Summary` prints the backend's utilisation block with the combination factors next to the own checks, plus their maximum deviation, and outputs `backend_utilization`. Worker flag `--design`.
- **compas_dlubal**: `DlubalClient` takes a `port` (or `DLUBAL_API_PORT`) - RFEM is not always on 9000.
- **compas_opensees**: surface samples now carry membrane forces and moments (`n_x n_y n_xy m_x m_y m_xy`), from the shells' Gauss-point stresses rotated into the surface frame and averaged per node; signs and axes as RFEM's mesh-node tables. Verified on one-way plates spanning x and y.
- **compas_dlubal**: WP0b-Rest - the plate calibration against RFEM (`tests/record_plate_rfem.py`, fixture `plate_rfem_calibration.json`, `test_rfem_plate_calibration.py`): deflection, centre moments and reactions agree between OpenSees and RFEM within 5 %. `DlubalImporter` takes `mesh_size` (RFEM's FE target length).
- **compas_opensees**: a second backend on openseespy - beams, releases and springs, rigid links, nodal/member loads, self-weight, one result set per load case with 9 stations (forces and the deflection line). `--backend opensees` in the worker, `opensees` on `Tekton Backend`. No licence, no key; the sticks model solves in 0.08 s. Calibrated against recorded RFEM results (`tests/unit/fixtures`).
- **tekton_gh**: `Tekton Visualize` draws the deformed shape — polylines through the RFEM stations, sections swept along them as vertex-coloured meshes, one colour per member; quantities `displacement | N | Vy | Vz | Mt | My | Mz | utilization`, `exaggeration` input, auto-scaled colour range. Geometry lives in `tekton_gh.visualize` (pure, tested).
- **compas_dlubal**: the result reader reads surface results per mesh node (global deformations, basic internal forces) into `StructuralSurfaceResult`.
- **tekton_gh**: `Tekton Display` draws surfaces (mid-plane extruded by the thickness, semi-transparent) and their edge connections; `Tekton Visualize` draws surfaces deformed and coloured from the mesh-node samples (quantities `n_x n_y n_xy m_x m_y m_xy v_x v_y displacement`).
- **examples**: `tekton_test_plates.ghx` - beams and plates in one definition; `plate_box_component.py` builds the CLT box from sliders.
- **compas_dlubal**: the result reader reads member deformations (`STATIC_ANALYSIS_MEMBERS_GLOBAL_DEFORMATIONS`) and merges them into the force stations.
- **compas_dlubal**: a failed calculation is reported with RFEM's own error text (`has_results()` + errors-and-warnings table) instead of empty results.
- **tekton_app**: the worker reads the API key from `TEKTON_API_KEY`, `DLUBAL_API_KEY`, or the repo's `.env`.
- **compas_timber_fea**: `reconstruct.structural_to_timber` rebuilds a TimberModel from a StructuralModel (beams exact: GUID, axis, section, orientation; plates when 1:1; results attached; joints not). GH component `Tekton To Timber`.
- **compas_timber_fea**: `results.samples_by_beam` projects member stations onto the physical beam axis without a timber model.
- **compas_timber_fea**: attached results carry the displacement vector per sample and in the envelope (plain tuples).
- **tekton_gh**: new `Tekton Upgrade` - one button replaces every Tekton component on the canvas with its installed template, wires carried by parameter name, report of dropped wires; runs after the solve (`tekton_gh.upgrade`).
- **tekton_gh**: `Tekton Display` gets a `geometry` toggle (member geometry off by default) and an icon; `Tekton To Timber` gets an icon; both listed in ICONS.md.
- **tekton_gh**: new `Tekton Display`, the model view: elements, connections (rigid/coupling/hinge/shared node), support symbols by condition with labels, load arrows and moment rings, reaction arrows; vertex-coloured meshes, text-dot labels. Logic in `tekton_gh.model_view`.
- **tekton_gh**: `build_value_list` kept as a compatibility shim so definitions with pre-2026-09-15 component instances open without errors.
- **tekton_gh**: `Tekton Results` reworked: samples and parameters as trees with t on the beam axis (was member-local), signed envelope (was absolute), JSON record, optional TimberModel input that returns the Beam objects in order; staleness check kept.
- **tekton_gh**: `Tekton Attach Results` delegates to `compas_timber_fea.results.attach_results_to_timber` (beam-parameter samples across segments) instead of its own member-local copy, and attaches every load case unless one is chosen.
- **tekton_gh**: `Tekton Backend` accepts a file path in `api_key`; `Tekton Run` and `Tekton Visualize` reload their runtime module on every solve.
- Windows build route for the `.ghuser` components (pythonnet, no Rhino needed) documented in `packages/tekton_gh/README.md`.

### Changed
- **tekton_gh**: sections inside the six ribbon groups (`exposure` per entry in `build_metadata.py`): Author splits into material / support / load cases + combination / loads / policies, Translate into translate + preflight / after-translate (Apply Loads, Support Nodes), Results into reading / showing, IO into timber model / analysis model. The table now also matches the hand-edited Visualize and Combination metadata, so regenerating no longer drops `facet_edges`/`mesh_edges`. `Tekton Area Load` has its icon.
- **tekton_gh**: `Tekton Member Load` `start`/`end` are relative to the whole beam again: `Tekton Apply Loads` maps the stretch onto the members the beam was split into (it used to apply 0.2..0.4 to every piece). Note: the RFEM mapper still writes every member load uniform over the full member, so a partial piece arrives in RFEM at full length.
- **tekton_gh**: Point, Member, Surface and Area Load hand their description over in a small carrier object (`.spec`); a bare dict output was unpacked by Grasshopper into its keys (and a dict in a list arrives as a .NET Dictionary), so none of them reached `Tekton Apply Loads` in Rhino 8. Apply Loads still takes plain dicts from scripts.
- **tekton_gh**: `Tekton Apply Loads` works on a copy of the model - a re-solve without Translate no longer stacks the loads onto those of the previous solve.
- **tekton_gh**: drop-downs attach themselves on placement again (Material Library, Joint Policy, Plate Policy, Backend, Support, Support Nodes, Load Case, Results, Visualize); the `menu` inputs are gone. `attach_value_list` guards against the replace-while-queued crash: once per instance, component-still-in-document check, nothing escapes the delegate.
- **compas_timber_fea**: a pinned connector carries its hinge on one end only (the end where a beam terminates); both ends hinged made the connector a pendulum bar and the model a mechanism.
- **compas_dlubal**: coupling type (21–24) is derived from the member's releases instead of hard-coded to hinge-hinge.
- **compas_dlubal**: results are queried with `get_results` (raw) instead of `get_result_table` (display table, empty for members and nodes).
- **tekton_gh**: the Grasshopper worker call passes `--delete-all` for rfem/rstab, matching the documented "every run rebuilds" contract.

### Fixed
- **compas_dlubal**: surfaces were pushed with RFEM's library variant of the timber grade as orthotropic 2D - E0 along the surface's local x, E90 (370 MPa for C24) across, axes the neutral model never set. A simply supported square plate came back as a one-way slab, 3.2x softer than Navier. The importer now overwrites the variant with the neutral (isotropic) stiffness: E0 both ways, nu and G from the material. Found by the plate calibration.
- **compas_dlubal**: an active timber design add-on left over in RFEM's base data (which survive `delete_all`) made every following non-design run calculate nothing; the importer switches it off when `design` is not requested.
- **compas_dlubal**: coupling types 21-24 are used only for a full hinge (all rotations free); a partial release such as the neutral `pinned` (torsion held) becomes a rigid member with an explicit hinge. Type 22 had freed the torsion the neutral model keeps - found by the OpenSees cross-check (2.5x softer grid).
- **compas_dlubal**: support reactions are now the force on the structure (RFEM reports the force on the support); matches OpenSees and the Display arrows.
- **compas_timber_fea**: translating the same TimberModel twice no longer doubles its plates - the model appends structural surfaces on every generation (and its `remove_plate_structural_surfaces` is a no-op: it passes `None`, which compas reads as "get"); the translator now clears them first.
- **compas_dlubal**: surfaces now calculate in RFEM - the library timber material (1D model) cannot carry a plate; the importer pushes an orthotropic-2D variant per material for the thicknesses.
- **tekton_gh**: `Tekton Run` no longer uses the backend's SAF filepath as the result path for rfem/rstab.
- **examples**: the plate box's slab sits on centre-line dimensions, so it shares nodes with the wall tops (was floating 9 cm above them).
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

