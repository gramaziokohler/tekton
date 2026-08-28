# Materials

*Status: 2026-08-28 — mostly open, direction is clear*

## The problem

Today a material is a **name string** (`{1: "C24"}`). That works for exactly one
backend: RFEM resolves `"C24 | EN 338:2016-04"` against its own library. It
fails everywhere else:

- **SAF** wants physical properties in the sheet — the exporter currently
  hardcodes C24-ish numbers for *every* grade, so a GL24h model exports with
  C24 stiffness.
- **OpenSees / Abaqus** (researchers use these — the model must work there)
  have **no material library at all**. An `elasticBeamColumn` wants E, G, A,
  Iy, Iz as numbers. Without real properties in the neutral model, those
  backends are impossible.

So: a name is a key, not a material.

## The plan: a material library with presets

A neutral `Material` carrying the full physical property set, plus a library of
presets keyed by grade name. Roughly:

```python
Material(
    name="C24",
    standard="EN 338:2016",
    density_mean=420,          # kg/m3
    density_k=350,
    E0_mean=11000,             # MPa, parallel to grain
    E0_k=7400,
    E90_mean=370,
    G_mean=690,
    # strengths (characteristic, MPa) — needed for design checks, not for FEA
    f_mk=24, f_t0k=14.5, f_c0k=21, f_vk=4.0,
    poisson=0.0,               # convention: ~0 for timber grillages
)
```

*(Numbers above from the commonly cited EN 338 table — verify against the
current edition before shipping. Same exercise for GL grades per EN 14080.)*

**Presets** for the usual suspects: C14–C30, GL24h/c–GL32h/c. A user writing
`material="C24"` gets the full preset. **Standard assumption**: if nothing is
communicated at all, C24 spruce — but stated in the assumptions report, never
silent.

**Overrides**: same pattern as the joint policy. Start from a preset, override
single properties (`Material.from_preset("C24", E0_mean=10500)`), overrides
serialize with the model. A **material editor** (table UI) came up in
discussion — sensible, but that's an authoring-layer concern (see workflow.md);
the data model just has to make it possible.

## Per-element materials

`material_id` exists on sections/thicknesses but is hardcoded to `1` — one
global material for the whole model. A model mixing C24 beams with GL24h
members can't be expressed. The data model supports it; the translator doesn't.
Needs an authoring source: where does a beam say what it's made of?
`Plate.material` exists in compas_timber but was `None` in every fixture;
beams have nothing. Candidate for an upstream attribute (workflow.md).

## Orthotropy

Timber is orthotropic (E0 vs E90 differ by a factor ~30). For **members** this
mostly doesn't matter — a beam bends about its axes and E0 rules. For **plates**
it matters a lot; that discussion lives in plate-model.md (layup, D-matrix,
span direction). The material library should carry E90 and G from day one so
the plate side has what it needs.

## What each backend needs

| | needs from us |
|---|---|
| RFEM | grade name matching its library string (works today) — properties optional |
| SAF | name + properties in the sheet (properties currently faked) |
| OpenSees | E, G (numbers; sections carry A/Iy/Iz) — nothing else exists |
| Abaqus | full engineering constants; orthotropic possible (good for CLT layups) |

The library is the single source; backends take the slice they can express.

## Open

- Build the `Material` dataclass + preset table (small, high value).
- Fix SAF to write real properties from it.
- Per-element material authoring (upstream attribute?).
- Grade values double-checked against current EN 338 / EN 14080 editions.
- Service class / load duration (kmod, kdef) — needed for design checks, not
  for the FEA itself. Park until design-check integration.

## Sources

- EN 338 (solid timber grades), EN 14080 (glulam)
- Current state: `core/model.py` (materials dict), `mapper_members.py`
  (MATERIAL_LIBRARY name map), `saf.py` (hardcoded properties — known wrong)
