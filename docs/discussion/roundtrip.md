# Roundtrip: getting results back onto the timber model

*Status: 2026-09-15 — the loop runs against a live RFEM 6: push, calculate,
member forces + member/nodal deformations + reactions back, deformed and
coloured in Grasshopper. Steps 1 and 5 of the order of work are done; what the
live run taught is under "What the first live run taught". Mapping to beams,
BackendMap, utilization and plate results are still open.*

## What "roundtrip" promises

The designer's loop: model out → calculate → **numbers back on the design
model**. Max deflection, utilization per member, support reactions — visible
where the design happens (Grasshopper), without opening RFEM. That's the
headline feature; everything below serves it.

## Getting data out of RFEM

Solved, and not the way the scaffold assumed. `get_result_table(table,
loading)` is the *pre-processed* table "as displayed in the desktop
application" — on the first live run it came back **empty for members and
nodes** while support forces arrived. `get_results(ResultsType, loading="LC1")`
is the raw database query and returned every row: 1648 member stations
(404 members × 11), 344 nodes, 4 supports. The reader uses `get_results` for
all four tables (`STATIC_ANALYSIS_MEMBERS_INTERNAL_FORCES`,
`STATIC_ANALYSIS_MEMBERS_GLOBAL_DEFORMATIONS`,
`STATIC_ANALYSIS_NODES_GLOBAL_DEFORMATIONS`,
`STATIC_ANALYSIS_NODES_SUPPORT_FORCES`); the column names
(`member_no, location_x, n, v_y, v_z, m_t, m_y, m_z`, `u_x … phi_z`,
`p_x … m_z`) matched the parsers' candidate lists on the first try.

The DataFrame → container parsers (`result_parsing.py`) are pure functions,
tested offline against recorded frames. Positions are normalised to 0..1 per
member; member deformations are merged into the force rows because RFEM
samples both on the same station grid.

Still untested: the timber design add-on's utilization table — *the* designer
number, and the next thing to try live.

## What the first live run taught (2026-09-15)

Four things, none visible offline:

1. **A failed calculation does not raise.** `calculate_all` returns an
   `OperationResult` with a message, `has_results()` is False, and the result
   queries come back empty. A solver error (instability) lands in
   `ERRORS_AND_WARNINGS_TABLE`; a model error (section with no area) leaves
   even that table empty. The reader checks `has_results()` after
   calculating and forwards the solver's text — otherwise the symptom is a
   silent "0 members, 0 nodes".
2. **Units.** The Dlubal API speaks SI base units, N and Nm; the neutral
   contract is kN and kNm. Loads went out 1000× too small, results came back
   1000× too large (194 "kNm" in an 8×10 cm beam under self-weight). One
   factor now sits in `compas_dlubal/conventions.py`, applied to loads on the
   way out and forces/moments/reactions on the way back. Sanity anchor: the
   sticks model's self-weight reactions sum to 5.2 kN (C24) — right in kN,
   absurd in N.
3. **Hinge-hinge couplings are pendulum bars.** The connector between two
   non-meeting centrelines was pushed as RFEM type 24 (hinged both ends),
   which carries axial force only; a beam hanging on four parallel ones is a
   mechanism ("stiffness matrix singular, node 39, direction Y"). The
   translator now puts the hinge on one end only (the end where a beam
   terminates; for crossings the second node), and the mapper derives
   21/22/23/24 from the releases. The joint policy still decides rigid vs.
   pinned; it only ever produced the two-hinge case by accident.
4. **The API key is mandatory locally too** (`UNAUTHENTICATED` without it),
   so the worker reads `TEKTON_API_KEY`, then `DLUBAL_API_KEY`, then the
   repo's `.env`.

## Mapping results back — the identity chain

```
RFEM member no  →  neutral member id  →  source_element_id (beam GUID)  →  Beam
```

The first two links are 1:1 today (member.no == neutral id), the third is
carried on every member. So *within one session* the chain works. Across
sessions it breaks: neutral ids derive from transient graph indices and shift
when the model is edited. Two fixes, both planned:

- write the neutral/source GUID into RFEM's `id_for_export_import` field on
  push, so the RFEM objects themselves carry the provenance;
- persist a **BackendMap** ({neutral id → backend no}, consulted before
  re-export so existing objects keep their numbers). The serializable model
  (done) is the prerequisite.

## The segmentation problem

FEA splits a physical beam into several members (at joints, at support
points). The compas_timber Beam knows nothing about that — and shouldn't.
Proposal from discussion, which I think is right:

**Attach results at parameters along the beam axis.** Each result row has a
position on a *segment*; segment start/end are known points on the beam
centerline, so every sample maps to a parameter t ∈ [0,1] on the *physical
beam*. Stored e.g. as:

```python
beam.attributes["analysis"] = {
    "provenance": {model_hash, load_case/combo, timestamp, source},
    "samples": [(t, {N, Vy, Vz, Mt, My, Mz, displacement}), ...],
    "envelope": {max_utilization, max_deflection, ...},
}
```

- The **envelope** (per-beam max/min) is what the designer sees first —
  colour a model by utilization, done.
- The **samples** keep the full picture for whoever wants diagrams.
- We do **not** hand back the analysis mesh. The designer asked about their
  beam, not about our discretization. (Debug view of the analysis model is a
  separate, legitimate feature.)
- Provenance is mandatory — a number without "which model state, which
  combination" is a liability, results silently outliving a design change is
  the worst failure mode here. Model-hash comparison should let us *warn*
  ("results are stale").

Plates, same pattern, harder: results at surface sample points map back to the
plate via `source_element_id` (fixed to be the real plate GUID now). Axis
convention matters — RFEM's m_x follows the surface axes, so `span_direction`
must be pinned before plate results are interpretable. Connection-line forces
(shear flow along a joint) are the screw-design quantity and deserve their own
container eventually.

## The workflow question (open, needs a decision)

Who is in this loop?

- **Designer loop** (clear): GH → translate → push → calculate → results back
  onto beams. RFEM is a headless engine; rebuild-on-every-run is fine *if*
  results attach via GUIDs, not numbers.
- **Engineer in the loop** (unclear, the interesting one): the engineer opens
  the pushed RFEM model, refines loads/supports/hinges, runs the real
  verification. Three sub-questions:
  1. Do their RFEM-side edits survive our next push? Today: no (delete_all) or
     collision chaos. Needs BackendMap + incremental update, or a declared
     "we own geometry, you own loads" split — and eventually *reading back*
     their loads/supports as overrides into the neutral model, so their work
     survives a design iteration.
  2. Do we let the engineer change the **timber model**? My take: no —
     the timber model is the designer's authority. The engineer works on the
     neutral model / RFEM level; what flows back are analysis results and
     override annotations (loads, supports, releases), never geometry.
  3. Does the engineer even see the neutral model? It's serializable JSON now,
     so it *can* be the exchange artefact ("here's the idealization, argue
     with the assumptions report") — cheaper than arguing inside RFEM.

## Order of work

1. ✅ Read member forces + deformations + reactions into the containers
   (offline-testable against recorded DataFrames). Live-verified 2026-09-15.
2. ✅ Map to beams via the identity chain, param-based, with envelope +
   provenance (`compas_timber_fea.results.attach_results_to_timber`, exposed
   as `Tekton Attach Results`). Samples include the displacement vector as a
   plain tuple so the attribute stays JSON-plain. Live: 84/84 beams, 11
   samples each. Still per session only — see 3. The reverse direction
   exists too (`compas_timber_fea.reconstruct.structural_to_timber`, GH
   `Tekton To Timber`): beams come back exactly from segments + section +
   orientation, GUIDs restored, results attached — joints do not, their
   types are not in the neutral model. So a StructuralModel JSON on its own
   is a complete handover artefact for the beam side.
3. ◐ GUIDs go into `id_for_export_import` on push (done); BackendMap not
   started — every run is `delete_all` + rebuild.
4. ☐ Utilization via timber design add-on (needs the live test).
5. ✅ Staleness warning: `Tekton Run` stamps the model fingerprint, `Tekton
   Results` compares and flags `stale`.
6. ☐ Plate results, connection forces — after the chain model.

## Sources

- `result_reader.py`, `result_parsing.py`; `tests/test-roundtrip.py` (shape of the loop)
- `get_results` / `get_result_table` behaviour observed live against RFEM 6 with dlubal-api 2.13.8, 2026-09-15
- `packages/tekton_gh/README.md` — the Grasshopper side of the loop, smoke-test numbers
- BackendMap / identity design: `../reviews/plattengraph_design_2026-08-27.md` §2.1
