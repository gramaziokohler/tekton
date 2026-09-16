# Discussion documents

Working notes on the open design questions of Tekton. Each document states what
we know, what we decided (and why), and what is still open. They are meant to be
argued with, not treated as spec.

| Document | Question |
|---|---|
| [loads-and-supports.md](loads-and-supports.md) | How do loads, load cases and supports live in the neutral model, software-agnostically? |
| [materials.md](materials.md) | Material library, presets, physical properties, overrides |
| [design-checks.md](design-checks.md) | Which EC5 checks Tekton computes itself, and what the neutral model still lacks for stability |
| [plate-model.md](plate-model.md) | How a plate is represented, and who tessellates |
| [software-comparison.md](software-comparison.md) | One table: how each target software wants things |
| [opensees-backend.md](opensees-backend.md) | OpenSees as a backend: what was verified, what an adapter needs |
| [roundtrip.md](roundtrip.md) | Getting results back and attaching them to timber elements |
| [workflow.md](workflow.md) | Who does what, where, in which package |
| [work-packages.md](work-packages.md) | Where Tekton stands against its goals (2026-09-15) and the plan: eight work packages in three phases |

Related, more detailed material:

- `../docs/review_2026-08-27.md` — full repo review + implementation log
- `../reviews/plattengraph_design_2026-08-27.md` — deep design study on the plate graph (German)
- `../docs/handoff.md` — one-page overview
