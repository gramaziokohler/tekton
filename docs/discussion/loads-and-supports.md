# Loads, load cases, supports in the neutral model

*Status: 2026-08-28 — partly implemented, partly open*

## The principle

Loads and supports are **authored on the neutral model**, never in a backend.
The moment a backend invents its own loading (which the Dlubal importer did,
with a hardcoded catalogue), the same model produces different analyses in
different software and the neutral layer is pointless. This is fixed: the
importer now consumes `model.load_cases`, `point_loads`, `member_loads`,
`load_combinations`.

A timber design model carries no loading, so the translator can only contribute
one thing honestly: **self-weight**. Everything else is engineering input that
gets added after translation.

## Load types

Three geometric kinds cover what every target software understands:

| Kind | Neutral object | Addresses | Status |
|---|---|---|---|
| Point load | `StructuralPointLoad` — force + moment vector (kN, kNm) | node id | ✅ implemented, exports to RFEM (×1000 → N at the Dlubal boundary, `conventions.py`, since 2026-09-15 — before that, loads arrived 1000× too small) |
| Line load | `StructuralMemberLoad` — force vector per length (kN/m), start/end param | member id | ✅ implemented (uniform), exports to RFEM (same factor) |
| Area load | — | surface id | ❌ missing |

Notes:

- Vectors, not magnitude+direction: the neutral model stores a full force
  vector; backends that want one direction per load object (RFEM) split it at
  their boundary. Keeps the neutral side simple and convention-free.
- Area loads on **beam-only** structures (a roof load on a rafter field) are a
  separate problem: someone has to distribute them. RFEM has load wizards /
  load panels for this — probably better to use those than to reimplement
  tributary-area logic. Open.
- Loads should eventually address **stable IDs** (see roundtrip.md) — e.g. a
  line load on a wall-base chain. Today they address transient node/member ids,
  which shift when the model changes.
- Trapezoidal/varying line loads, free polygon loads, thermal loads: not yet,
  add when someone needs them.

## Load cases

A load case is a named bucket with an **action category** — that category is
what drives code-based combination generation (EC0), so it must survive into
the backend. Implemented as:

```python
StructuralLoadCase(id, name, action_category, self_weight)
# action_category: PERMANENT | VARIABLE | SNOW | WIND  (extend as needed)
```

Default when nothing is authored: one self-weight case. That is the honest
minimum — a designer pressing "run" gets gravity, nothing invented.

**Combinations**: `LoadCombination(id, name, factors={case_id: factor})` exists
and exports to RFEM. What we do *not* do (yet, maybe ever): generate the EC0
combinatorics ourselves. RFEM has a combination wizard driven by the action
categories; letting it do the work avoids reimplementing a norm. But SAF /
OpenSees / Abaqus have no wizard — for those, either we generate combinations
or the engineer authors them. Open question, leaning: implement a small EC0
generator later, it is well-defined and testable.

## Supports

Per-DOF stiffness, one convention everywhere: `inf` = rigid, `0` = free,
finite = spring. Same convention as member releases — learn once, use
everywhere.

| Kind | Status |
|---|---|
| Nodal support (6 DOF) | ✅ implemented |
| Line support (wall base!) | ❌ missing — plates have no support story at all |

Where supports come from: explicitly marked `support_points` on beams
(an attribute the designer sets), never geometric guessing ("lowest nodes").
That stays. Plates need an equivalent authoring mechanism — probably marked
edges → line supports.

A model with no supports is a mechanism. Nothing warns about that today;
belongs in the preflight check (see review, step 8).

## Presets, like materials?

The material-library idea (see materials.md) partially transfers: standard
**load case sets** are plausible presets — e.g. "residential" = self-weight +
imposed cat. A 2.0 kN/m² + snow by zone. But load *values* depend on location
and code, so presets should be conveniences with visible values, never silent
defaults. Only self-weight is safe to assume.

## Open

- Area loads (data model + RFEM surface load mapping — proto exists).
- Line supports + plate support authoring.
- Load distribution for beam-only roofs: our job or RFEM load panels?
- EC0 combination generator: build or delegate per backend?
- Where does the designer author loads — GH components, GUI, upstream
  attributes in COMPAS Timber? (see workflow.md)

## Sources

- Implemented model: `packages/compas_timber_fea/src/compas_timber_fea/core/model.py`
- RFEM load protos verified against the pinned `dlubal-api 2.13.8` wheel
  (`NodalLoad`, `MemberLoad`, `LoadCombination.ItemsTable`, action categories)
- EN 1990 (EC0) for combination logic, EN 1991 for load values
