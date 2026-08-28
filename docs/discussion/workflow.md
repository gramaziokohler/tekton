# Workflow: who does what, where

*Status: 2026-08-28 — responsibilities settled, authoring story open*

## Package responsibilities

```
compas_timber  →  compas_timber_fea  →  compas_dlubal / compas_saf / (future adapters)
(geometry &        (neutral model,        (backend vocabulary,
 idealization       policies, units,       nothing else)
 solvers)           serialization)
```

| Layer | Owns | Explicitly does *not* own |
|---|---|---|
| `compas_timber` (branch) | Idealization **geometry**: segment splitting, node merging, mid-planes, connector segments, the structural graph | Mechanics, units, backends |
| `compas_timber_fea` | The neutral `StructuralModel`; joint & plate policies (joint → release); unit contract; serialization; assumptions report; (soon) preflight | Any backend convention — no Z-flips, no β angles, no name strings for RFEM |
| `compas_dlubal` | RFEM/RSTAB vocabulary: protos, β conversion, Z-down, library name resolution, result tables | Deciding anything — it translates decisions |
| `compas_saf` | SAF sheets, spec conformance | same |
| `tekton_app` | GUI/CLI packaging of the above for non-Python users | Logic — it calls the libraries |

Rule of thumb that has caught every architecture bug so far: **if a value
depends on which software you're talking to, it belongs in the adapter; if it
depends on engineering judgment, it belongs in the neutral layer as an
explicit, overridable, reported policy.**

## Where the user authors things

This is the honest gap. The *data model* can now hold materials, loads, load
cases, combinations, supports, releases — but the *authoring story* is thin:

| Input | Today | Target (proposal) |
|---|---|---|
| Support points | ✅ attribute on Beam, set by designer | keep; add plate-edge equivalent |
| Material | one global name string | per-element upstream attribute + material editor table (see materials.md) |
| Loads / load cases | Python only (author on the neutral model) | GH components + presets; maybe upstream attributes for element-bound loads |
| Combinations | Python only | preset sets / EC0 generator or RFEM wizard |
| Joint releases | Python policy object | policy presets + per-instance override, eventually visual (pick a joint, set it) |

**The upstream question** (raised in handoff): should some of this live in
COMPAS Timber itself — load cases, materials as element attributes, set at
design time? Arguments for: one model, no second authoring layer, attributes
travel with the design. Against: loading is engineering input with a different
author and lifecycle than geometry; polluting the design model with analysis
state couples the two models we deliberately separated. Middle ground that
feels right: **element-bound facts upstream** (material, support points,
maybe element-bound loads like cladding weight), **analysis-bound decisions in
the neutral layer** (load cases, combinations, policies, overrides). Same
split as geometry vs. mechanics.

## The two personas, concretely

**Designer** (Grasshopper): builds the timber model, marks supports, picks a
material, presses run. Gets envelope numbers back on beams (see roundtrip.md).
Should never have to see RFEM. This loop justifies **GH components** — the
natural interface for this user:

- *Translate* (timber model → structural model, policies as inputs)
- *Author* (material, load case, load, support — small components, presets)
- *Run* (push + calculate + read back; RFEM headless)
- *Inspect* (view analysis model, assumptions report, colour by utilization)

Nothing in the current stack blocks this — translator and importer are plain
Python calls; components are wiring. GUI stays for the no-Rhino case.

**Engineer**: receives either the RFEM model (today's handoff) or, better, the
serialized neutral model + assumptions report — reviewable, diffable,
argueable. Refines loads/supports/releases. Open questions about whether and
how their edits flow back live in roundtrip.md. They do *not* edit the timber
model.

## Open

- Build the GH components (thin, after the roundtrip lands — a run component
  without results back is half a loop).
- Decide the upstream-attribute split with the compas_timber maintainers.
- Material editor (table UI) — where does it live? GH? tekton_app? Both read
  the same library.
- Assumptions report: exists as a list of strings on the translator; needs to
  become a proper artefact the engineer receives (part of the serialized
  model? separate document?).
- tekton_app's role once GH components exist — probably: the engineer-side
  viewer + batch runner, not the primary authoring surface.
