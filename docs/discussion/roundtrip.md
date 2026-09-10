# Roundtrip: getting results back onto the timber model

*Status: 2026-08-28 — scaffold exists, the real thing is next. This is the
design discussion for it.*

## What "roundtrip" promises

The designer's loop: model out → calculate → **numbers back on the design
model**. Max deflection, utilization per member, support reactions — visible
where the design happens (Grasshopper), without opening RFEM. That's the
headline feature; everything below serves it.

## Getting data out of RFEM

Solved in principle: `get_result_table(table, loading)` returns a DataFrame
(verified the signature against the pinned wheel; the reader scaffold already
triggers calculation correctly). What's left is choosing tables (member
internal forces, nodal deformations, support reactions — plus the timber
design add-on's utilization table, **untested**, and worth testing early
because utilization is *the* designer number) and writing DataFrame → neutral
result containers. The containers (`StructuralResultSet` etc.) are already
shaped for it: per-load-case, per-member lists with positions.

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

1. Read member forces + deformations + reactions into the containers
   (offline-testable against recorded DataFrames).
2. Map to beams via the identity chain, param-based, with envelope +
   provenance.
3. Write GUIDs into `id_for_export_import` on push; persist BackendMap.
4. Utilization via timber design add-on (needs the live test).
5. Staleness warning (model hash).
6. Plate results, connection forces — after the chain model.

## Sources

- `result_reader.py` scaffold; `tests/test-roundtrip.py` (shape of the loop)
- get_result_table signature verified against dlubal-api 2.13.8
- BackendMap / identity design: `../reviews/plattengraph_design_2026-08-27.md` §2.1
