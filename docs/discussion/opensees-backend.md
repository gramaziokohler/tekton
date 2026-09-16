# OpenSees as a backend

*Status: 2026-09-16 — **implemented for beams** as `packages/compas_opensees`,
wired into the worker (`--backend opensees`) and the `Tekton Backend`
drop-down, calibrated against RFEM on the sticks model and run from
Grasshopper. The spike (`tests/spike_opensees.py`) remains the evidence for
the mapping table; `tests/unit/test_opensees_backend.py` guards it. What the
implementation taught is in "What building it taught" below. Every ✅ in the
table was run and checked against a closed-form solution. ◐ = documented but
not run. ❌ = tried, does not work.*

## What building it taught (2026-09-16)

- **It works, and it is fast.** The sticks model (344 nodes, 304 beams,
  100 couplings with one-sided hinges): 0.08 s to solve, 0.5 s for the
  whole worker call, 6.6 s from the Grasshopper button including process
  start and JSON. RFEM: 25 s. That is the speed at which `Tekton Run` could
  stop being a button.
- **Cross-backend calibration found a bug in the RFEM mapper.** With the
  same model, OpenSees gave 6.8 mm, RFEM 17 mm. The cause: RFEM's coupling
  type 22 frees *all three* rotations at the hinged end; the neutral
  `pinned` release keeps torsion. Freeing torsion in OpenSees reproduced
  RFEM to 5 %. The Dlubal mapper now uses the coupling types only for a
  full hinge and a rigid member with an explicit hinge otherwise, so RFEM
  sees the release the neutral model states. Whether a lap joint transfers
  torsion is a joint-policy question (WP2) - the backends now at least
  agree on what they were asked.
- **Signs, measured instead of assumed.** Across the 200 beams, midspan
  against midspan: OpenSees' `sectionForce` My, Mz and P carry RFEM's sign
  as they are - the spike's "sagging positive" assumption about RFEM was
  wrong. The shear derived from the end forces is opposite to RFEM's.
  Reactions: RFEM reports the force on the support, OpenSees the force on
  the structure; the neutral model now defines the latter (the Dlubal reader
  negates). Fixture: `tests/unit/fixtures/sticks_rfem_calibration.json`.
- **RFEM runs g = 10 m/s².** Self-weight reactions differ by exactly
  10/9.81. The adapter keeps 9.81; the calibration test scales.
- **RFEM includes shear deformation** (Timoshenko members); OpenSees'
  elastic section does not. With timber's G/E = 1/16 that is a few percent
  on deflections - the residual after gravity.
- **Lobatto is capped at 10 points.** 11 stations (RFEM's count) is
  refused; the adapter uses 9, which keeps a station at midspan.
- **A fully fixed system aborts the process**, not the analysis: LAPACK's
  `DGBSV` complains about parameter 9 and Python is gone. The builder counts
  free DOFs and refuses before OpenSees sees it.
- **Deflection along a member** is not an OpenSees result for
  `forceBeamColumn`. The reader integrates the curvature M/EI from the
  station moments twice (the moment line is a polynomial the Lobatto
  stations interpolate exactly), pinned to the end displacements. Midspan sag
  of the test beams to all printed digits, in both bending directions.
- **A simply supported beam in 3D needs a fork.** Two supports that both
  free rx let the beam spin about its own axis; OpenSees refuses (correctly),
  and the adapter turns the non-zero return into an exception naming the
  case. The test models use a fork support at one end.
- **Ghost nodes for releases** use stiff springs (1e10) for the fixed DOFs
  rather than `equalDOF`, because the releases are in the member's local
  axes and `equalDOF` ties global ones. Conditioning was fine on every model
  tried.

## Why bother

Two reasons, and the second is the bigger one:

1. **Researchers use it** (handoff.md). A model that only runs in RFEM is a
   model the research side cannot touch.
2. **It is pip-installable and headless.** Every backend Tekton has today
   either needs a licensed desktop application (RFEM/RSTAB) or produces a
   file nobody solves in CI (SAF). OpenSees would be the first backend that
   turns the *whole chain* — translate → solve → results → attach to beams —
   into an automated test. Today `tests/unit` stops at "the protobuf messages
   look right".

## Distribution and runtime — what is actually on PyPI

| Package | Version / date | Python | Wheels |
|---|---|---|---|
| `openseespy` (meta) | 3.8.0.0 / 2026-03-18 | ≥3.10 | pure; pulls one of the three below |
| `openseespywin` | 3.8.0.0 | **≥3.12** | `win_amd64` only |
| `openseespymac` | 3.8.0.0 | ≥3.10 | `macosx_13_0_arm64` only — **Intel Macs dropped** |
| `openseespylinux` | 3.8.0.0 | ≥3.12 | x86_64 |
| `opensees` (OpenSeesRT, PEER) + `xara` shim | 0.1.31 / 2026-07-17 | cp39–cp313 | `win_amd64`, manylinux x86_64; no macOS wheels seen |

What that means for Tekton:

- **Fits the existing worker route.** The repo venv is already 3.12; OpenSees
  runs in `tekton_app.worker` exactly like RFEM does, minus gRPC and the API
  key. Not in Rhino's 3.9 — same boundary as today, nothing new to invent.
- **Windows on ARM (this machine):** `openseespy/__init__.py` refuses to import
  when `platform.machine()` says ARM64, although the AMD64 Python in the venv
  loads the AMD64 DLL fine under emulation. `import openseespywin.opensees`
  bypasses the gate; the adapter needs that fallback (or an upstream fix —
  the check is on the host, not the interpreter).
- **OpenSeesRT / xara** ships a cp39 `win_amd64` wheel, so it could in
  principle run *in-process* in Rhino 8 on Windows. It claims to be a
  drop-in for the openseespy command surface. Experimental (0.x, "opensees"
  package name), no macOS wheels. Not the first choice, but a reason to write
  the adapter against the plain openseespy command API and nothing fancier —
  it keeps that door open.
- **compas_fea2_opensees is not a shortcut.** Checked the source
  (fea2/compas_fea2_opensees, last push 2025-06, not on PyPI): it writes a
  `.tcl` and shells out to a separately installed `OpenSees.exe`; beam end
  releases are `raise NotImplementedError`; there are no member line loads;
  results go through `.out` files into SQLite; compas_fea2 pins
  `sqlalchemy==1.4`. It would put a second neutral model between ours and
  the solver and still leave the parts we need unimplemented. Decision:
  native adapter on openseespy.

## Mapping: neutral model → OpenSees

Units: the neutral model is kN, m, kNm and OpenSees is unitless, so the
numbers go in as they are — only `E`, `G` become kN/m² (`MPa * 1000`).
Z-up stays Z-up. No conventions module needed for axes or units; the
cantilever and simply supported beam came out exact to all printed digits ✅.

| Neutral | OpenSees | Status / rule |
|---|---|---|
| `StructuralNode` | `node(tag, x, y, z)`, `model basic -ndm 3 -ndf 6` | ✅ |
| `Material` + `StructuralSection` | numbers on the element: `A, E, G, J, Iy, Iz` | ✅ — **`J` is not in the neutral model**; the adapter computes it for rectangles (`β·b³·h`). E from `E0_mean`, G from `G_mean`. |
| `StructuralMember` | `elasticBeamColumn` + `geomTransf Linear vecxz` | ✅ — neutral stores local **y**; OpenSees wants the local x–z plane, so `vecxz = x_axis × orientation_vector`. Vector, not angle: no β-angle business as in RFEM. |
| Release, `inf`/`0` only, bending | `-releasey` / `-releasez` code 1/2/3 on the element | ✅ — **rule:** if *every* member at a node releases the same rotation, that DOF is held by nothing and the matrix is singular ✅ observed. Fix: keep one member continuous, or `fix` that DOF at the node (identical deflection ✅). |
| Release, finite spring, or torsion/translation | duplicate node + `zeroLength(-orient x, y)` with `uniaxialMaterial Elastic k` per spring DOF + `equalDOF` for the rigid DOFs | ✅ exact (`PL³/3EI + PL²/k`). `-orient` takes the member's local axes, so `MemberRelease` stiffnesses stay in local coordinates as authored. No release code exists for `rx`, `ux`, `uy`, `uz` — those always go this route. |
| `is_rigid` / RIGID / COUPLING | `rigidLink beam` | ◐ kinematics fine ✅, **but reactions at the retained node are 0 under every constraint handler** (Transformation, Penalty, Lagrange) ✅ observed — OpenSees sums reactions from element forces only. Use a stiff `elasticBeamColumn` (×1e4) instead ✅ (tip deflection within 1e-4). |
| `MemberEccentricity` | `geomTransf ... -jntOffset dXi dYi dZi dXj dYj dZj` (global) | ◐ not run |
| `StructuralSupport` | `fix` for `inf`; finite → `zeroLength` to a fixed ghost node | ✅ / ◐ (same construction as the spring release) |
| `StructuralPointLoad` | `load(node, Fx, Fy, Fz, Mx, My, Mz)` | ✅ |
| `StructuralMemberLoad` | `eleLoad -ele -type -beamUniform Wy Wz Wx [a/L b/L Wyb Wzb Wxb]` | ✅ full and partial (reactions exact). **Local axes** — the neutral vector is global, so project onto local x/y/z. |
| `self_weight` | nothing automatic | beams: `ρ·A·g` projected to local axes as `-beamUniform` ✅; shells: `ShellMITC4` honours `-selfWeight gx gy gz` via the section's ρ ✅ (sign to calibrate), DKGT/DKGQ/NLDKGQ/ASDShellQ4 **silently ignore it** ❌. |
| `StructuralLoadCase` | one `pattern Plain` per case; `analyze`, read, `remove loadPattern`, `wipeAnalysis`, `reset` | ✅ cases come out independent. |
| `LoadCombination` | no wizard | linear analysis → superpose case results in the reader, or run a factored pattern. Either way the EC0 generator question (loads-and-supports.md) becomes real here. |
| `StructuralSurface` | **no mesher** — tessellate in the adapter, then `ShellDKGT` (tri) / `ShellDKGQ`, `ShellMITC4` (quad) + `ElasticMembranePlateSection(E, ν, t, ρ)` | ✅ SS square plate within 1 % of Timoshenko on an 8×8 grid. OpenSees's own `mesh tri` is the PFEM one (Tri31, plane) — not usable for shells. Candidates: `triangle` (holes, area constraint, planar — project the plate, mesh, lift) or gmsh for quads. |
| area loads on surfaces | `-surfaceLoad` | ❌ ignored by every shell tested; only a stdout warning. → consistent nodal loads from tributary areas, built by the adapter. |
| `span_direction` / orthotropy | `LayeredShell` over `PlateFiber(ElasticOrthotropic)` | ✅ defines, not solved. CLT-ready once layup data exists (plate-model.md). Shell local x follows node ordering — order each element's nodes along `span_direction`, or use ASDShellQ4's `-local` option ◐. This is where a mirror bug would hide. |
| `StructuralSurfaceConnection` (line hinge) | duplicate node rows along the shared edge + `zeroLength` springs | blocked **upstream**: needs conforming meshes on both plates along the edge, i.e. the shared BorderChain from plate-model.md, which the neutral model does not have yet. Not an OpenSees limitation. |

## Results → `StructuralResultSet`

| Neutral | OpenSees | Status |
|---|---|---|
| `StructuralNodeResult.displacement/rotation` | `nodeDisp(tag)` | ✅ global, m / rad |
| `reaction_force/moment` | `reactions()` then `nodeReaction(tag)` | ✅ kN / kNm — but see rigid-link caveat above |
| `StructuralMemberResult` at ends | `eleResponse(tag, 'localForce')` → `[N, Vy, Vz, T, My, Mz]` at i, then at j | ✅ end forces only |
| `StructuralMemberResult` along the member (`position` 0..1) | `forceBeamColumn` + `section Elastic` + `beamIntegration Lobatto N`; `sectionLocation` gives the stations, `sectionForce(tag, s, dof)` the forces (`P, Mz, My, T`) | ✅ exact (`q·x·(L−x)/2` at all five stations). Recommended over splitting members: one element per member, N stations, positions known. |
| `StructuralSurfaceResult` | `eleResponse(tag, 'stresses')` → per Gauss point `[n11 n22 n12 m11 m22 m12 q13 q23]` | ✅ 32 values (4 GP × 8; also for DKGT). kN/m and kNm/m directly. **Element-local axes** → tie to `span_direction`. |
| solver failure | `analyze()` returns non-zero; messages on stdout from C++, never a Python exception | ✅ observed. Per-element warnings (`addLoad - load type unknown`) do **not** fail the run. |

**Sign convention is the open calibration.** With a downward load, the
midspan `sectionForce My` came out `−10.0` where "sagging positive" is
`+10.0`; `localForce My` at end j likewise `−10.0`. This is the same
silent-corruption spot software-comparison.md warns about, only it is now
testable offline: one canonical model (cantilever, SS beam with UDL, hinge,
spring) run through OpenSees, compared in `tests/unit` against recorded RFEM
numbers — which pins the Dlubal parsers' signs at the same time.

## What an implementation needs (written before it existed - kept as the plan it was)

1. **`packages/compas_opensees`** — a workspace member shaped like
   `compas_dlubal`: `builder.py` (StructuralModel → ops commands, in the
   importer's object order), `analysis.py` (the per-load-case loop),
   `result_reader.py` (→ `StructuralResultSet`), `conventions.py` (kN/m²
   scaling, local-axis projection, section constants incl. `J`, the sign
   calibration). `openseespy>=3.8` as an optional extra with the ARM64 import
   shim. Preflight runs first, as in `DlubalImporter.run`.
2. **Wiring** — `--backend opensees` in `tekton_app/worker.py`; `VALID` in
   the `tekton_backend` component; `run_backend` without `--delete-all` and
   without an API key. The GUI/CLI in `__main__.py` get a flag if wanted.
3. **Beam-only first.** Nodes, members, both release routes, stiff-beam rigid
   members, nodal supports, point/member loads, self-weight, one result set
   per load case with `forceBeamColumn`/Lobatto stations. Everything above
   marked ✅ — the spike script already is most of the mapping. Order of
   magnitude 300–500 lines plus tests.
4. **Calibration fixture** (item 3's test) — the canonical model against
   closed-form values and against recorded RFEM output. This is the first
   test that exercises `attach_results_to_timber` on real solver output.
5. **CI** — pip install on a Linux x86_64 runner; `tests/unit` gains an
   end-to-end case behind `pytest.importorskip("openseespy")`.
6. **Plates** — the tessellation module (`triangle` vs gmsh to decide; target
   size as an adapter parameter, never in the neutral model), nodal area
   loads, shell self-weight per element type, `span_direction` → element
   axes. Depends on the BorderChain for anything with connections; a
   single free plate works today.
7. **Later** — `-jntOffset` eccentricities, line supports (once the neutral
   model has them), EC0 combinations, `LayeredShell` for CLT.

## Meshing for plates: which library, and the property that decides it

*Measured 2026-09-16, before WP5 starts. Scripts: the benchmark in this
section is reproducible from the numbers below.*

OpenSees has no mesher. RFEM does, which is why the neutral model carries
**no mesh at all** — a surface is a polygon of node ids, and the plate design
study (`../reviews/plattengraph_design_2026-08-27.md`, F1/F3) is explicit
that tessellation must not enter the neutral layer: it destroys plate
identity and thereby the result mapping. The same study leaves exactly one
door open — tessellation "inside a Karamba-like backend adapter". OpenSees is
that kind of backend, so the mesher belongs in `compas_opensees`, nowhere
else.

**The decisive property is not mesh quality. It is conformity.** Two plates
sharing an edge must end up with *identical* nodes on it; otherwise the
plates are not connected and the model has a crack that solves happily and
reports nonsense.

Measured on two 4x3 plates sharing an edge, each meshed on its own:

| Library | Available (py3.12) | Boundary honoured | Conforming shared edge |
|---|---|---|---|
| `compas_cgal` 0.10.0 | yes | **no — adds its own boundary nodes** | **no** |
| `gmsh` 4.15.2 | yes | yes, with `setTransfiniteCurve` | **yes, at every target size** |
| `libigl` 2.6.3 | yes | n/a | n/a — a processing library, exposes no 2D mesher |

The CGAL result is the interesting one. `refined_delaunay_mesh` produced a
correct, good-looking mesh (holes respected, input corners kept) — and still
split the shared edge differently on the two sides: 8 nodes against 10 at a
0.5 m target. Pre-densifying the shared edge with identical vertices on both
sides did **not** fix it: the refiner adds boundary nodes regardless, even at
irregular positions (a 4 m edge at target 1.0 came back with a node at 0.5).
At a 0.75 m target the two sides happened to agree — which is worse than a
consistent failure, because it looks like it works.

gmsh conformed at 0.3, 0.5 and 0.75 m, with identical triangle counts on both
plates, because `setTransfiniteCurve` *prescribes* the node count on a curve.
That is precisely what a BorderChain is: a shared edge whose subdivision both
neighbours must accept.

**Consequence for WP5.** The mesher is gmsh, driven per plate, with every
shared edge prescribed from the BorderChain so conformity is guaranteed by
construction rather than hoped for. `compas_cgal` stays a reasonable choice
for anything where only one polygon is meshed at a time — it is not one here.
The mesh lives in the adapter and never in the neutral model; results come
back per plate through `source_element_id`, not per triangle.

Open: the free (non-shared) edges may be meshed freely, so the target length
is a mesh *hint* and not part of the model. And gmsh is a 60 MB dependency
that initialises global state — same discipline as openseespy: one model per
process, `finalize()` in a `finally`.

## Risks

- **Silent failures are the norm, not the exception.** Unsupported element
  loads, constraint reactions, singular matrices — all report on stdout and
  carry on. The adapter must never emit a command it has not proven, and the
  worker must check `analyze()`'s return value and fail loudly.
- **Torsion constant `J`** is computed by the adapter for now; if a second
  backend ever needs it, it belongs in `StructuralSection`.
- **Platform gate** on Windows-ARM; openseespy 3.8 has no Intel-Mac wheel.
- **Global state.** openseespy is one model per process. Fine under the
  worker (fresh process per run); a problem only if someone drives it from a
  long-lived process — `wipe()` at the start of every build.
- **Shell results in element-local axes.** Node ordering decides the axes;
  the mapping to `span_direction` needs its own asymmetric test model.

## Sources

- Spike: `tests/spike_opensees.py` (this repo), openseespy 3.8.0.0 on
  Windows 11 ARM64, AMD64 Python 3.12.12 under emulation
- PyPI JSON for `openseespy*`, `opensees`, `xara`, `compas_fea2*` (2026-09-15)
- openseespydoc.readthedocs.io: `eleLoad`, `mesh`, `ShellMITC4`;
  opensees.github.io: `elasticBeamColumn` (`-releasey/-releasez`)
- github.com/fea2/compas_fea2_opensees — `problem/problem.py`,
  `model/releases.py`, `problem/loads.py`
- github.com/peer-open-source/xara README
