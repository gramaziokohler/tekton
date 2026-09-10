# Example definitions

## `tekton_smoke_test.ghx`

The smoke test: shows the whole chain on an example model, from loading it to
the exported file. Built and run through on 2026-09-10 in Rhino 8.

```text
Panel(model path) ─→ [Load Timber] ─┬─→ [Find Supports] ─┐
                                    │                    ↓
                                    └──────────→ Tekton Support ─→ Tekton Translate ─┬─→ Tekton Preflight
                                                                          ↑           ├─→ Tekton Inspect
                                                     Panel(repo path) ────┘           └─→ Tekton Run ←── Tekton Backend
                                                                                              ↑
                                                                                          Toggle
```

What the definition demonstrates:

- **Tekton Info** finds the repo, the compas_timber branch and the worker venv.
- **Translate** turns 84 beams into 344 nodes and 404 members, with an
  assumptions report.
- **Support** sets 4 support points; **Preflight** then reports
  "no findings" (before that: "no supports — mechanism").
- **Run** starts the worker subprocess and writes a SAF file
  (404 members, 4 supports) — the path Rhino → backend works.

### Before opening it for the first time

**Adjust the two path panels.** They contain absolute paths from this machine
(repo root and test model) — on another computer they point nowhere. That is
the price of the definition running without further setup; the alternative
would be a relative path, which Grasshopper does not know, because a `.ghx`
knows nothing about its own location.

The repo path only has to be set **once**: components with a `repo` input
store it for the session, and all the others find it there.

### The two script components

`Load Timber` and `Find Supports` are test helpers, not Tekton components:

- **Load Timber** loads a `TimberModel` from JSON. COMPAS Timber ships no
  building block for that, but Tekton starts where a model is already on the
  canvas.
- **Find Supports** takes the lowest beam ends as support points. In a real
  design the designer sets those themselves.

### Toggle

The toggle on `Tekton Run` is set to `False`, and that is deliberate: a run
blocks Grasshopper and rebuilds the backend model from scratch. It is pressed
on purpose, not triggered in passing.


## `plate_box_model.json` + `build_plate_model.py`

A plate model that makes structural sense: four CLT wall panels forming a
closed box, plus a floor slab. Built by the script next to it, so the geometry
is reproducible and the reasoning is in the source rather than locked inside a
JSON file.

Run it with the repo venv:

```bash
.venv/bin/python packages/tekton_gh/examples/build_plate_model.py \
    packages/tekton_gh/examples/plate_box_model.json
```

What it exercises that the beam smoke test does not: mid-plane generation,
plate-to-plate connections, thickness handling, and the span direction that
decides how plate results are read.

### Two findings from building it

**Everything sits on centre-line dimensions, and that is not cosmetic.** The
idealisation works with mid-planes, and a connection is only found where one
plate's edge lies *in* the neighbouring plate's mid-plane. A model that merely
looks right - walls standing under a slab - produces no coupling at all and
falls apart into loose pieces.

**Wall-to-slab coupling does not currently work**, which is why the box carries
itself through its four vertical corners and the slab sits on top as a separate
surface. The cause is upstream in compas_timber (`structural.py`): the
mid-surface frame is built as `Frame(origin, direction, normal)`, which puts the
plate normal into the frame's *y*-axis - so `frame.normal` ends up lying **in**
the plate plane. The connection finder projects onto that normal, so it only
matches plates whose (wrong) normals happen to align. Wall-to-wall does,
wall-to-slab does not. The same mix-up feeds Tekton's `span_direction`, which
reads `frame.xaxis`.

Consequence for the example: preflight reports the model splitting into two
parts. That warning is correct and should stay visible until the upstream frame
is fixed - it is the model telling the truth about itself.

**Plates carry no supports either.** The translator reads `support_points` off
beams only, so a plate model reaches analysis unsupported. `TektonSupportNodes`
closes that on the analysis side: pick nodes by level or by point and support
them directly.
