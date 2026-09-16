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
| Designer loop | **Works end to end** for beams and plates: translate → preflight → RFEM → forces, deformations, reactions → deformed and coloured on the canvas, numbers per beam, results attached to beams. Missing: utilisation. |
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

## WP1 — Utilisation

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
Phase A  (designer number)     WP1 utilisation  →  WP3 loads  →  WP4 supports
Phase B  (timber layer)        WP2 joints from fasteners  →  WP5 plates second half  →  WP7 materials
Phase C  (engineer handoff)    WP6 stable ids + BackendMap + read-back
```

A before B because a designer with utilisation for real load combinations
can already use Tekton daily, even with default joints. B is the substance
that makes Tekton timber-specific. C is the largest and touches the
workflow decision; it should not block A and B.

Total, rough: A ≈ 5 days, B ≈ 8 days, C ≈ 5–7 days, plus one live RFEM
session per package. Every package ends with its finding written into the
matching discussion document and its example definition updated.

## Explicitly out of scope here

- OpenSees / other backends (`software-comparison.md`): after C, as a
  second adapter that proves the neutral layer.
- LCA, building physics, IFC (`handoff.md`, open question): after the
  structural loop is complete — "deepen first, then widen".
- Karamba-style embedded component UI: a C# front-end layer, considered
  only once the data behind it (WP3, WP4) exists.
