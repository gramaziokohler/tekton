# Design checks: what Tekton verifies itself

*Status: 2026-09-18 - WP1b implemented, WP1 (RFEM's add-on) read and
compared; see "The comparison" below. Written 2026-09-16 as WP1b started.
The clause numbers are EN 1995-1-1 (Eurocode 5).*

> **⚠ Not verified by an engineer.** Every value and every clause below was
> transcribed by a developer reading the standard. A wrong `k_mod` or a
> misread interaction formula produces numbers that look completely
> plausible — no crash, no outlier, and the unit tests assert against the
> same transcribed values, so they cannot catch it either. Until a
> structural engineer has reviewed both the tables and the clause logic,
> treat Tekton's design numbers as orientation during design (comparing
> variants, spotting the obviously undersized member), not as verification.
> The values are the base Eurocode recommendations; CH, DE and AT national
> annexes deviate. This document is the place to start that review.

## Why compute checks ourselves at all

RFEM has a timber design add-on, and reading its ratios is WP1. So why
write our own?

- **The OpenSees backend has no add-on.** It solves a frame in
  milliseconds, in CI, without a licence — and would stay without a design
  number. Half of Tekton's testability lives there.
- **A licence should not be needed to ask "is this beam too small".** The
  designer loop is meant to be usable before anyone opens RFEM.
- **A read ratio is opaque.** A number arrives; which check produced it,
  and under which assumptions, does not. A check we compute can name its
  governing criterion and print the factors it used.
- **Two independent paths are how errors surface.** WP0 calibrated
  OpenSees against recorded RFEM numbers and thereby found a wrong coupling
  mapping and a reaction sign error. The same applies here: our ratio
  against RFEM's ratio is a test, not a duplication.

The two are therefore complementary, and the comparison between them
belongs in this document once both exist.

## What the model gives us, and what it does not

Verified against `core/model.py` and `core/materials.py` on 2026-09-16.

**Available.** Section forces per member and location (`axial`, `shear_y`,
`shear_z`, `torsion`, `moment_y`, `moment_z`), node displacements and
rotations, reactions, section geometry (`width`, `height`, `shape_type`),
and characteristic material strengths: `f_mk`, `f_t0k`, `f_c0k`, `f_vk`,
plus `E0_mean`, `E0_k`, `G_mean` and the densities.

**Missing, and not derivable from the geometry** — this is the reason the
checks are split across WP1b and WP1c:

| Missing | Needed for | Why it cannot be derived |
|---|---|---|
| `service_class` (1/2/3) | `k_mod`, `k_def` | A property of the building |
| `load_duration_class` | `k_mod` | `action_category` on the load case is related but not the same |
| `gamma_M` | design values | A choice of code and national annex |
| buckling length / β | `k_c` (6.3.2) | Depends on bracing the FE model does not represent |
| `l_ef`, load application point | `k_crit` (6.3.3) | Depends on fork supports and where the load acts |

Until WP1c adds these to the model, `k_mod` and `γ_M` are **component
inputs** with documented defaults, and the report always prints the values
it used. A silent default here would be the one thing worse than no check.

Also missing today, but pure geometry and therefore unproblematic: section
area, second moments of area, section moduli, and member length. WP1b adds
them as properties on `StructuralSection` / `StructuralMember`.

## Design values

```text
f_d = k_mod · f_k / γ_M
```

`k_mod` comes from EN 1995-1-1 Table 3.1 as a function of service class and
load-duration class; for a combination of actions, it is taken from the
action with the *shortest* duration in that combination (3.1.3). `γ_M`
follows Table 2.3 — 1.3 for solid timber, 1.25 for glulam and LVL.

Defaults used when nothing is set: service class 1, load duration
"medium-term", γ_M = 1.3. These are stated in every report, and they are
assumptions, not results.

## The checks

### Implemented in WP1b (no stability assumption needed)

| Check | Clause | Note |
|---|---|---|
| Bending, both axes | 6.1.6 | with `k_m` = 0.7 for rectangular sections |
| Tension parallel to grain | 6.1.2 | |
| Compression parallel to grain | 6.1.4 | cross-section only, no buckling |
| Shear | 6.1.7 | factor 1.5 for the rectangular stress distribution |
| Bending + tension | 6.2.3 | linear interaction |
| Bending + compression | 6.2.4 | quadratic in the axial term |

`k_h` (size factor, 3.2/3.3) is derivable from the section height and is
available as `DesignAssumptions(size_factor=True)`. **Off by default**: EC5
says "may", RFEM's add-on leaves it off by default
(`k_h_solid_timber_bending = false`), and omitting it is the safe side -
it only ever raises the strength. The report prints which.

### Deferred to WP1c (needs the model extension)

| Check | Clause | Blocked on |
|---|---|---|
| Buckling | 6.3.2 | buckling lengths per axis |
| Lateral-torsional buckling | 6.3.3 | `l_ef`, load application point |
| Combined bending + compression with stability | 6.3.2 | both of the above |

Until then, every report states explicitly that stability was not verified.
An unverified check must never look like a passed one.

## The comparison: own checks vs RFEM's add-on (2026-09-18)

Sticks model (`tests/unit/fixtures/sticks_structural.json`, 304 timber
members, C24, 8/10 cm), RFEM 6.13 timber design under CO1 = 1.35 * self-
weight, service class 1, permanent duration, gamma_M = 1.3, stability off.
Our checks were fed RFEM's own CO1 section forces, so the comparison
isolates the formulas from the solver (the solver side is WP0's
calibration).

| RFEM governing check | members | our ratio / RFEM's - 1 |
|---|---|---|
| 6.2.4 bending + compression | 174 | -5e-6 ... +1.4e-5 |
| 6.1.6 / 6.2.3 bending (+ tension) | 30 | +3e-6 ... +1.8e-3 |
| "negligible internal forces" (ratio 0) | 100 | - |

With `size_factor=True` every bending-governed member sat a constant
**-7.8 %** below RFEM - exactly 1/k_h for h = 100 mm, (150/100)^0.2 =
1.0845 - which is how the RFEM default was found. Our shear check (6.1.7)
never governs on this model and is compared only implicitly; torsion
shear (6.1.8) is in RFEM's table and not in ours. Pinned in
`tests/unit/test_rfem_timber_design.py` against the recorded table.

Where the two numbers meet in the product: `Tekton Summary` prints both
blocks - "Utilisation (rfem timber design, loading LK1)" with the
combination's factors, and "Utilisation (own EC5 checks)" - plus the
maximum deviation between them. Without WP3 our checks run per load case
and RFEM's for its combination, so on the sticks model that line reads
26 % (= 1.35 - 1); it is a labelled caveat, not a discrepancy.

## Open questions

- **Buckling lengths: authored or computed?** A `Design Policy` component
  would have the user set β per member — defensible, but tedious on a large
  model. An OpenSees eigenvalue analysis could deliver them instead.
  Worth a spike with a test case before the interface is fixed.
- **Load combinations.** Without WP3 the checks run per load case, which
  for self-weight alone is not a design situation. The combination factors
  belong to WP3; this document only consumes them.
- **Plates.** Surface results carry membrane forces and moments; the
  corresponding checks for panel materials are a separate question and are
  not covered here.
- **Which national annex.** The defaults above are the recommended values.
  A Swiss or German annex changes `γ_M` and some factors.

## Related

- [work-packages.md](work-packages.md) — WP1, WP1b, WP1c, WP1d
- [materials.md](materials.md) — where the characteristic strengths come from
- [opensees-backend.md](opensees-backend.md) — the backend that needs these
  checks most
- [roundtrip.md](roundtrip.md) — how results get back to the elements
