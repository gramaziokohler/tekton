# Work packages: from pipeline to idealisation

*Status: 2026-09-15 — written after the first live roundtrips (beams and
plates). The pipeline goal is met; this is the plan for the idealisation
goal. Dependencies and order are proposals, argue with them.*

## Where this starts from

Tekton promises three things (see [handoff.md](handoff.md)): derive an
**idealised structural model** from a timber model, **store** it, and
**communicate** it to analysis software — in two modes, the *designer loop*
(RFEM as a calculation engine, numbers back on the canvas) and the
*engineer handoff* (the model as the engineer's working basis).

As of 2026-09-15:

| Goal | State |
|---|---|
| Designer loop | **Works end to end** for beams and plates: translate → preflight → RFEM → forces, deformations, reactions → deformed and coloured on the canvas, numbers per beam, results attached to beams. Missing: utilisation (WP1/WP1b) and a report that summarises a run (WP1d). |
| Storage | **Solved.** Neutral model + results round-trip through JSON; `To Timber` rebuilds beams exactly from it. |
| Communication | **Half.** RFEM/RSTAB live, SAF as file. Handoff is one-way: the engineer's RFEM edits die on the next push. |
| Idealisation | **A third.** Containers and policies have the right shape; the rules that fill them with engineering content (fasteners → stiffness, loads → combinations, design → utilisation) are defaults. |

The work packages below turn the last row into the first.

## Principles that every package follows

- **Engineering decisions are explicit, overridable, reported.** A policy
  decides, the assumptions report says what it decided and why, the user
  can override per type or per instance. Never a silent default.
- **Backend-agnostic in the neutral layer, backend-specific in the adapter.**
  A rule that depends on RFEM belongs in `compas_dlubal`; a rule that depends
  on engineering judgment belongs in `compas_timber_fea`.
- **Offline-testable first.** Every package lands with unit tests that run
  without Rhino or RFEM; the live check against RFEM is the last step, not
  the first, and its findings go into `roundtrip.md`.
- **The canvas shows it.** A new mechanical concept is not done until
  `Display` draws it and `Results`/`Visualize` read it.

---

## WP0 — OpenSees backend (done for beams, 2026-09-16)

**Why.** The first backend without a licence or a desktop application:
the whole chain - translate, solve, results, attach - runs in CI, and a
solve takes milliseconds instead of 25 seconds. Details and findings in
[opensees-backend.md](opensees-backend.md).

**Done.** `packages/compas_opensees`: builder (nodes, supports, beams as
`forceBeamColumn` with 9 Lobatto stations, releases and springs as ghost
nodes + `zeroLength`, rigid links as stiff beams), per-case analysis loop,
reader (nodal results, reactions, station forces, deflection line by
curvature integration), worker flag, backend drop-down entry, 15 tests
including a cross-backend calibration against recorded RFEM numbers. The
calibration fixed the coupling mapping and the reaction sign in the RFEM
adapter.

**Open.** Plates (tessellation, nodal area loads, shell self-weight per
element type, `span_direction` → element axes; single free plates first,
connected ones after the BorderChain); line supports; `-jntOffset`
eccentricities; combinations by superposition; a "live" mode of `Tekton
Run` that recomputes on the slider now that a solve is cheap.

**Size of what is open.** Plates two to three days; the live mode a day.

## WP1 - Utilisation, read from the backend

*Done 2026-09-18 for members: `Tekton Backend` -> `design`, ratios per
station in `metadata["utilization"]` with the governing check named,
`Tekton Results`/`Visualize` quantity `utilization`, `Tekton Summary` prints
RFEM's block next to ours. Comparison in design-checks.md; what the add-on
needs (one GUI step) in roundtrip.md. Surfaces, and combinations beyond the
wizard's 1.35 * G, wait for WP3/WP5.*

**Why first.** It is *the* designer number, the one thing the loop still
cannot deliver, and every later package (loads, joints) is judged by it.

**Scope.**
- Activate RFEM's timber design add-on for the pushed model (add-on flag,
  design situation, the pushed load cases in a combination).
- Read the design ratio table via `get_results` (member design ratios by
  location) into `StructuralMemberResult.metadata["utilization"]` and, for
  surfaces, into the surface samples.
- Surface it: `Visualize`/`Results`/`Attach Results` already carry
  `quantity="utilization"`; make it non-zero, with the governing check
  named in the sample metadata.
- Envelope per beam in `beam.attributes["analysis"]`.

**Depends on.** Nothing. Benefits from WP3 (without combinations the ratio
is for self-weight only).

**Deliverables.** `compas_dlubal` reads the ratio table; a
`tests/unit` parser test on a recorded frame; `roundtrip.md` records what
the add-on needs; the smoke test shows a utilisation colouring.

**Acceptance.** Sticks example: every beam shows a ratio > 0 for the
self-weight case; the governing check is readable per beam.

**Size.** One live session to learn the add-on's API, then a day.

**Relation to WP1b/WP1c.** This package *reads* a ratio that RFEM computed.
It therefore needs RFEM, its add-on and its licence, and it says nothing for
the OpenSees backend or for an offline check. WP1b computes the same number
in the neutral layer, from forces and material. The two are not redundant:
having both is how we find out whether our own check agrees with a
certified one — the same trick WP0 used when it calibrated OpenSees against
recorded RFEM numbers.

---

## WP1b — Utilisation, computed in the neutral layer (done, 2026-09-16)

**Why.** Three reasons the backend read (WP1) cannot cover. It needs RFEM,
so the OpenSees backend — the one that runs in CI in milliseconds — stays
without a design number. It needs a licence and the timber add-on, so
"is this beam too small" costs a desktop session. And it is opaque: a ratio
arrives, the check behind it does not. A check we compute ourselves is
testable offline, runs for every backend, and can name what governed.

**Scope.** Everything that needs no stability assumption, i.e. everything
whose inputs are already in the neutral model:
- Section properties on `StructuralSection` — `area`, `moment_of_inertia_y/z`,
  `section_modulus_y/z` — and `length` on `StructuralMember`. Pure geometry,
  no engineering assumption, missing today.
- Stresses from the section forces already returned: σ_m,y, σ_m,z (bending),
  σ_t,0 / σ_c,0 (axial), τ (shear, with the 1.5 factor for rectangles).
- Design values: `f_d = k_mod · f_k / γ_M`, with `k_mod` looked up from
  service class × load-duration class per EC5 Table 3.1, and `γ_M` per
  material type. Both are *inputs*, defaulted and always reported —
  never silently assumed.
- The checks that follow from EC5 6.2.3/6.2.4 and 6.1.6/6.1.7: bending
  about both axes with `k_m`, tension and compression parallel to grain,
  shear, and the bending+axial interactions.
- Per member: the governing check, its ratio, its location along the member.
- Explicitly *not*: buckling (6.3.2) and lateral-torsional buckling (6.3.3).
  They need a buckling length, which the model does not have — that is WP1c.

**Depends on.** Nothing. Benefits from WP3 (combinations) exactly as WP1
does. Independent of WP1 — and worth doing *before* it, because it needs no
live RFEM session.

**Deliverables.** `compas_timber_fea/design/` with the section properties,
the `k_mod` table and the checks; `Tekton Summary` (WP1d) surfaces it;
`tests/unit/test_design_checks.py` against hand-calculated values from a
textbook example; a `docs/discussion/design-checks.md` recording the clauses
used and, once WP1 exists, the comparison against RFEM's ratios.

**Acceptance.** A single-span beam under self-weight reproduces the
hand-calculated bending ratio to within rounding. The report names the
governing check and the assumed `k_mod`/`γ_M`. Runs with `backend=opensees`
and no licence anywhere.

**Size.** Two days, half of it EC5 reading and test-case construction.

---

## WP1c — Stability, and what the neutral model is missing for it

**Why.** The honest limit of WP1b. Buckling and lateral-torsional buckling
are what decide slender timber members, and neither can be computed from
the neutral model as it stands. This package is mostly a *model* package,
not a formula package.

**What is missing.** Verified by grep against `core/model.py` — none of
these exist today:

| Missing | Needed for | Why it cannot be derived |
|---|---|---|
| `service_class` (1/2/3) | `k_mod`, `k_def` | A property of the building, not of the geometry |
| `load_duration_class` per load case | `k_mod` | `action_category` is close but not the same thing |
| `gamma_M` | `f_d` | A choice of code and national annex |
| buckling lengths / β per member and axis | `k_c` (6.3.2) | Depends on bracing a beam FE model does not know |
| `l_ef`, load application point | `k_crit` (6.3.3) | Depends on fork supports and where the load sits |

`k_h` (size factor) is the exception: derivable from `height`, trivial.

**Scope.**
- Extend `StructuralModel`: `service_class` and `gamma_M` on the model,
  `load_duration_class` on `StructuralLoadCase`, `buckling_length_y/z` (or
  β factors) and lateral-restraint data on `StructuralMember`.
- Serialisation, defaults and migration: an older JSON must still load,
  with the new fields at documented defaults.
- A `Tekton Design Policy` component in `1 | Author` that sets them —
  the same role Joint Policy and Plate Policy play: an engineering
  decision the geometry does not carry, authored explicitly and reported.
- Then the checks: 6.3.2 with `k_c`, 6.3.3 with `k_crit`, and the combined
  bending+compression interaction.
- Alternative worth a spike before committing to β inputs: take buckling
  lengths from an OpenSees eigenvalue analysis instead of from the user.
  Cheaper for the user, harder to defend per member — decide with a test
  case, not in the abstract.

**Depends on.** WP1b (the checks it extends). Touches `core/model.py` and
`core/serialization.py`, so it wants coordinating with whatever else is
mid-flight in those files.

**Deliverables.** The model fields plus migration test; `Design Policy`
component and icon; the stability checks with tests; `design-checks.md`
extended with the assumptions and their defaults.

**Acceptance.** A slender column under axial load reproduces a
hand-calculated `k_c` and the interaction ratio. An old serialized model
still loads. The assumptions report names every stability assumption used.

**Size.** Three to four days, plus the eigenvalue spike if we take it.

---

## WP1d — Tekton Summary (the analysis report) (done, 2026-09-16)

**Why.** Today the results are on the canvas as numbers per beam and as
colour. What is missing is the one-page answer to "how did this model do" —
the thing you read before you trust anything else, and the thing you hand
over. It is also where a model error shows up fastest: a reaction sum that
does not match the applied load is visible in one line.

**Scope.** A component in `4 | Results`, bundle `tekton_summary`, nickname
`TSummary`, accent `#8f50d3`:
- Deformations: maximum and mean, per load case, with the node or member
  where the maximum sits; span/deflection ratio where a span is known.
- Reactions: sum per direction against the applied load total — the
  equilibrium check that catches a wrong support or a lost load.
- Section forces: extremes per component (N, V, M) with their location.
- Utilisation: from WP1b when computed, from WP1 when the backend
  delivered it; the governing check named; the worst members listed.
- Model facts: nodes, members, surfaces, supports, load cases, and the
  assumptions that were in force (`k_mod`, `γ_M`, service class, and
  explicitly which checks were *not* run).
- Output: a readable text report as a string (panel-ready), single value
  outputs for the headline numbers so they stay usable downstream, and an
  optional CSV — one row per member — for the spreadsheet.

**Depends on.** WP1b for the utilisation section; works without it, and
then says so instead of printing a zero.

**Deliverables.** `tekton_gh/components/tekton_summary`, the report builder
in `tekton_gh/src` (so it is testable without Rhino), unit tests on a
recorded result model, an entry in `ICONS.md` and an icon.

**Acceptance.** Run the sticks example: the report names max deflection and
where it is, the reaction sum matches the applied load within tolerance,
and — with WP1b — the governing check per worst member. CSV opens in Excel
with one row per member.

**Size.** A day and a half, most of it in what the report should say rather
than in code.

**Done.** `compas_timber_fea/design/` (sections, factors, checks) with 23
tests against hand calculations; `tekton_gh/summary.py` with 16 tests;
`Tekton Summary` in `4 | Results` with its icon. Verified on the sticks
model through the OpenSees backend: 404 members, max displacement 6.8 mm at
node 180, governing check "bending + compression" (6.2.4) at 0.200 under
self-weight with the defaults. Changing the assumptions moves the number the
way it should — service class 2 / short-term / γ_M 1.25 takes the same model
to 0.128. The equilibrium check declines to compare when self-weight or
member loads are in play, rather than comparing against a partial sum.

---

## WP2 — Joint policy from the joint itself

**Why.** Today a joint is rigid or pinned by its *class name*. The timber
layer Tekton promises decides from the *connection*: fasteners, geometry,
grain direction. This is where Tekton stops being a converter.

**Scope.**
- A `JointRule` that reads a compas_timber joint and its fasteners (count,
  diameter, direction, spacing) and returns a `MemberRelease`: rigid,
  pinned, or a **spring** with K_ser per EC5 (the spring path already
  reaches RFEM as a hinge with stiffness).
- Rules for the joint classes in use (X-lap, T-butt, L-miter, L-butt), with
  the rule's reasoning in `describe_for()` so the assumptions report says
  "T-butt, 4 screws Ø8 at 45°: K_ser = … kNm/rad → spring".
- `Tekton Joint Policy` grows: per-type and per-instance overrides stay;
  add "from fasteners" as a preset, and an `overrides` tree input.
- `Display`: hinge markers show the rule's outcome (spring vs pinned
  distinguishable).

**Depends on.** Fastener data on the compas_timber joint — check what the
branch exposes; if nothing, this package starts with a `fasteners`
attribute convention and a note upstream.

**Deliverables.** `core/joint_rules.py` + tests per rule; policy preset;
report lines; `discussion/joints.md` with the EC5 formulas used.

**Acceptance.** Sticks example: the assumptions report lists the rule per
joint; changing screw count on one joint changes its release and the
result. No two-hinge couplings ever generated (already guaranteed).

**Size.** Two to three days, half of it EC5 reading.

---

## WP3 — Loads as a catalogue

**Why.** Utilisation without combinations is a number for self-weight.
The Karamba screenshot is the target: EN 1990 categories, ψ/γ, design
situations, combinations generated — not typed.

**Scope.**
- `core/load_catalogue.py`: EN 1990 action categories with ψ0/ψ1/ψ2 and γ;
  imposed load classes A–H; snow and wind as categories (values by zone are
  the user's, the category carries the factors).
- `StructuralLoadCase` gets a category from the catalogue;
  `StructuralLoadCombination` gets a generator: ULS/SLS persistent,
  accidental optional, from the cases present.
- `Tekton Load Case`: category from a drop-down that lists the catalogue
  (the auto-menu mechanism); `Tekton Load Combination`: "generate EN 1990"
  button plus manual factors.
- Mapper: combinations to RFEM (`LoadCombination`) and design situations;
  the reader reads results per combination (`loading="CO1"` works like
  `"LC1"`).
- Area loads on plates (`StructuralSurfaceLoad`) — the plate example has
  only self-weight today.

**Depends on.** Nothing hard; WP1 needs it to be meaningful.

**Deliverables.** Catalogue module + tests; combination generator + tests;
two components extended; the plate example gets an imposed load and a
combination.

**Acceptance.** Plate example: LC1 self-weight + LC2 imposed cat. A →
generated ULS combination → utilisation from WP1 for the combination.

**Size.** Two days.

---

## WP4 — Supports, authored

**Why.** The symbols now render all 64 stiffness combinations; the
authoring cannot produce most of them. Plates get supports only through
`Support Nodes`.

**Scope.**
- `Tekton Support` and `Support Nodes`: `support_type` grows to the RFEM
  set (pinned, fixed, roller x/y, sliding, hinged with fixed rotation
  axis) plus an explicit six-value input and spring stiffnesses.
- Line supports for plates (wall feet as a line, not four nodes):
  `StructuralLineSupport` → RFEM `LineSupport`; `Support Nodes` gets a
  `line` mode.
- Support reactions per line in the reader.

**Depends on.** Nothing.

**Deliverables.** Container + mapper + reader + tests; both components.

**Acceptance.** Plate example with a line support under each wall; the
Display symbol row matches RFEM's for every authored type.

**Size.** One to two days.

---

## WP0b — OpenSees for plates (meshing in the adapter)

**Why.** WP0 left plates out: OpenSees has no mesher, and the neutral model
carries no mesh by design. Closing it makes the licence-free backend able to
run the same models as RFEM, in CI, in milliseconds — and it is the first
place where Tekton has to mesh anything itself.

**The decision, measured** (2026-09-16, `tests/spike_meshers.py`, written up
in [opensees-backend.md](opensees-backend.md)). The question is not mesh
quality, it is **conformity**: two plates sharing an edge must get identical
nodes on it, or the model has a crack that solves and reports nonsense.

- `compas_cgal` 0.10.0 meshes one polygon well (holes, corners kept) but
  **refines the boundary on its own** — 8 nodes against 10 on a shared edge
  at a 0.5 m target, and pre-densifying both sides identically does not stop
  it. At 0.75 m the sides happened to agree, which is worse than a
  consistent failure.
- `gmsh` 4.15.2 conformed at every target tried, because
  `setTransfiniteCurve` *prescribes* a curve's node count — exactly what a
  BorderChain is.
- `libigl` 2.6.3 exposes no 2D mesher; it is a processing library.

**Scope.**
- gmsh in `compas_opensees` only — never in the neutral layer. The plate
  study (`../reviews/plattengraph_design_2026-08-27.md` F1/F3) permits
  tessellation exactly here, "inside a Karamba-like backend adapter",
  because subdivision upstream destroys plate identity and the result
  mapping with it.
- Mesh per plate, every shared edge prescribed from its BorderChain so
  conformity holds by construction; free edges may be meshed freely.
- `ShellMITC4`/`ShellDKGT` with an orthotropic section from the layup, the
  element axes driven by `span_direction` (WP0's open item, and the reason
  it needs an asymmetric test model).
- Nodal area loads and shell self-weight per element.
- Results back **per plate** via `source_element_id`, never per triangle —
  the mesh is internal to the run and must not leak into the model.

**Depends on.** Nothing hard. Single free plates first, connected ones once
the BorderChain exists (plate study §2.1). Benefits from WP1b, which then
gives plates a design number too.

**Deliverables.** `compas_opensees` meshes and builds surfaces; a conformity
test asserting two neighbouring plates share the same nodes on the edge; a
cross-backend calibration against recorded RFEM plate numbers, the way WP0
did for beams; gmsh as a dependency with its global state handled
(`finalize()` in a `finally`, one model per process).

**Acceptance.** The plates example solves through OpenSees; a two-plate
model shows identical nodes on the shared edge; deflection and m_x agree
with RFEM within the same tolerance band WP0 established for beams.

**Size.** Three to four days; the calibration is the long pole.

**Progress (2026-09-16).** Step 1 of the scope, the mesher, is done:
`compas_opensees/meshing.py` with 23 tests. The whole assembly goes into
**one** gmsh model, so an edge shared by two plates is one curve object used
by both faces — conformity is then a property of the geometry, not something
to be checked afterwards. Shared edges get `setTransfiniteCurve` from the
same target on both sides. Verified: two plates conform at 0.3/0.5/0.75/1.0 m
with evenly spaced seam nodes; three plates in a row conform at both seams;
a non-coplanar wall-on-slab pair conforms along its edge (the WP5 case); an
L-shaped outline keeps 12 m² rather than filling its notch; outline vertices
keep their neutral node ids, so results can still map back per plate. gmsh is
initialised and finalised around each call, so repeated meshing in one
process is safe.

**Progress (2026-09-16, later).** The shells too: `ShellDKGT` per triangle on
an `ElasticMembranePlateSection`, self-weight as consistent nodal loads, and
surface samples in `StructuralSurfaceResult`. Validated against the Navier
solution for a simply supported square plate — −3.3 % at a 0.5 m target,
−0.8 % at 0.25 m, walking towards the closed form as the mesh refines; the
reaction sum matches the self-weight exactly. The real 4-plate test model
solves in 0.09 s (600 shells).

Two findings worth keeping:

- **Orthotropy does not survive OpenSees' plate path.** The honest route
  (`ElasticOrthotropic` → `PlateFiber` → `LayeredShell`) builds without
  error but does not transport the material axes: a 30:1 stiffness ratio
  came out as 1.2:1 in deflection, while the same test on an isotropic
  section reproduced a factor of 30 exactly, so it is not the element. The
  section is therefore isotropic and every plate carrying a
  `span_direction` gets a warning saying the result is direction-agnostic.
  For CLT that matters, so plates still go to RFEM when the answer has to be
  defensible. Fixing it needs either a material with working axes or an
  equivalent-stiffness formulation per direction.
- **A unit mismatch used to hang, not fail.** A millimetre model translated
  as metres asks gmsh for ~10^9 triangles inside C++, where it neither
  returns nor honours a Python timeout. `meshing.py` now estimates the mesh
  size first and refuses with a message naming the likely cause — the same
  failure mode `core/units.py` warns about, one layer down.

Still open from the scope: membrane forces and moments per plate (the
element reports them in its own axes, and without working orthotropy that
convention is not yet pinned down), line supports, and the cross-backend
calibration against recorded RFEM plate numbers.

---

## WP5 — Plates, second half

**Why.** Surfaces push, calculate, draw. The numbers do not reach the
plates, the connections are not what the timber says.

**Scope.**
- `Results`/`Attach Results` for surfaces: envelope per plate (max
  deflection, max m_x/m_y, max n), samples as (point, values), written to
  `plate.attributes["analysis"]`.
- Wall-to-slab as a line connection with a policy (hinged/continuous/
  spring), not a rigid shared node. Blocked by the upstream frame bug in
  `compas_timber.structural` (mid-surface frame puts the normal in Y);
  fix it there first, then the connection finder sees wall-to-slab.
- `Plate Policy` from fasteners, analogous to WP2 (screw lines along the
  edge → K_ser per metre).
- `To Timber` for subdivided plates (merge patches to one outline).
- Span direction as an input on the plate, not only derived.

**Depends on.** Upstream fix for the frame bug (small, in the branch we
already pin); WP2 for the fastener rule.

**Deliverables.** Surface results on plates + tests; line connection with
policy + tests; upstream PR for the frame.

**Acceptance.** Plate example: wall-to-slab edge shows as a hinge in
Display, the slab's m_x envelope is on the plate attribute, a rebuilt
TimberModel from the JSON has the plates.

**Size.** Three days plus the upstream round-trip.

---

## WP6 — Stable IDs and the engineer handoff

**Why.** Today every push is `delete_all`. Whatever the engineer changed in
RFEM is gone. That makes the handoff one-way, and it makes results
unattachable across sessions (neutral ids shift with every edit).

**Scope.**
- **Stable neutral ids**: derive member/node ids from source GUID + segment
  index instead of graph order, so an unchanged beam keeps its numbers
  across translations. Serialised with the model.
- **BackendMap**: `{neutral id → RFEM no}` persisted next to the JSON;
  on push, update existing objects and only create/delete the difference
  (`--incremental` on the worker, `delete_all` stays the default until
  proven).
- **Read-back of overrides**: loads, supports and hinges the engineer added
  in RFEM come back as override entries in the neutral model — flagged
  as "from backend", shown in Display, kept on the next push.
- `Attach Results` across sessions then works by construction.

**Depends on.** Nothing technical; conceptually on a decision about who
owns what (`workflow.md`: designer owns geometry, engineer owns loads/
supports/releases — proposed, not decided).

**Deliverables.** Id scheme + tests; BackendMap; incremental push; read-back
for the three object types; `roundtrip.md` updated with the decision.

**Acceptance.** Push, add a support in RFEM by hand, push again with a
changed beam: the support survives, the beam is updated in place, results
attach to the same beam GUID.

**Size.** A week; the read-back is the uncertain part.

---

## WP7 — Materials per element

**Why.** One grade for the whole model is a placeholder. Real projects mix
C24 joists and GL24h beams and CLT plates.

**Scope.**
- Grade per beam/plate from `beam.attributes["material"]` or a `Tekton
  Material` assignment component (element list + grade).
- Translator maps to per-element `material_id`; sections and thicknesses
  reference the right one; the surface variant (orthotropic 2D) per grade.
- CLT layups as a material for plates (EN 16351 style: layer count,
  thickness, orientation) — RFEM's multilayer surface.
- The `Tekton Material` component stops being a placeholder.

**Depends on.** Nothing; WP5 for the layup-on-plate part.

**Deliverables.** Per-element mapping + tests; component; the plate
example uses a CLT layup.

**Size.** Two days; layups another two.

---

## WP8 — Housekeeping (continuous)

Not a package, a list to drain alongside:

- Icons for Material Library and Support Nodes (still placeholders).
- `Inspect` draws surfaces; `Results` for surfaces (part of WP5).
- Retire `tekton_test_*.ghx` and `tekton_test_plates_2.ghx`; keep
  `tekton_beams.ghx`, `tekton_plates.ghx`, `tekton_smoke_test.ghx`.
- Sphinx docs are placeholders; either fill `docs/*.rst` from the READMEs or
  drop Sphinx.
- The GUI (`tekton_app.gui`) blocks during export and stores the API key in
  clear text — decide whether the GUI is still a target now that the
  Grasshopper side exists.
- Commit discipline: 2026-09-15 left ~30 changed files uncommitted; the
  changelog under `[Unreleased]` is the commit message source.

---

## Order and phases

```text
Phase 0  (done)                WP0 OpenSees for beams
Phase A  (designer number)     WP1b own checks  →  WP1d Summary  →  WP1 backend ratio
                               →  WP3 loads  →  WP4 supports  →  WP1c stability
Phase B  (timber layer)        WP0b OpenSees plates  →  WP2 joints from fasteners
                               →  WP5 plates second half  →  WP7 materials
Phase C  (engineer handoff)    WP6 stable ids + BackendMap + read-back
```

A before B because a designer with utilisation for real load combinations
can already use Tekton daily, even with default joints. B is the substance
that makes Tekton timber-specific. C is the largest and touches the
workflow decision; it should not block A and B.

Within A, WP1b comes before WP1: it needs no licence and no live session,
so it can be written and tested the same day, and it gives WP1 something to
be compared against. WP1d follows immediately because it is what makes the
numbers readable. WP1c is deliberately last in A — it extends the neutral
model, and that is worth doing once the checks around it have settled.

Total, rough: A ≈ 5 days plus ≈ 5 for WP1b–d and WP1c, B ≈ 8 days,
C ≈ 5–7 days, plus one live RFEM session per package. Every package ends
with its finding written into the matching discussion document and its
example definition updated.

## Explicitly out of scope here

- OpenSees for plates and the live-solve mode: WP0's open half, after A.
- Other backends (`software-comparison.md`): after C.
- LCA, building physics, IFC (`handoff.md`, open question): after the
  structural loop is complete — "deepen first, then widen".
- Karamba-style embedded component UI: a C# front-end layer, considered
  only once the data behind it (WP3, WP4) exists.
