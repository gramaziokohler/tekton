# Example definitions

## `tekton_smoke_test.ghx`

The smoke test: shows the whole chain on an example model, from loading it
to the results on the canvas. Built 2026-09-10 (SAF export); on 2026-09-15 it
ran the full RFEM roundtrip on Windows against a live RFEM 6 — see the
numbers in [../README.md](../README.md#smoke-test).

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
- **Run** starts the worker subprocess. With backend `rfem` it pushes 754
  objects, calculates (~25 s) and brings back forces, deformations and
  reactions; with `saf` it writes an xlsx (404 members, 4 supports).
- **Visualize** (wired to Run's `structural`) draws the deformed system lines
  and the sections swept along them, coloured by `quantity`. Set
  `exaggeration` to ~100 and `quantity` to `My` to see the self-weight
  bending; the scale runs to the model maximum unless `high` is given.

### Before opening it for the first time

**Pick the backend.** The panel on `Tekton Backend` reads `rfem`; `saf` only
needs the `filepath` panel (the xlsx target). For `rfem`, RFEM 6 must be
running and the API key must be reachable — leave `api_key` empty and keep it
in the repo's `.env` (`DLUBAL_API_KEY=...`). Every run empties the open RFEM
model and rebuilds it, so have a scratch model open.

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


## `tekton_plates.ghx` (and `tekton_beams.ghx`)

The plate example; the beams pipeline lives in `tekton_beams.ghx` (the
combined `tekton_test_plates.ghx` was the intermediate step). Both carry a
`Tekton Upgrade` so a rebuilt set of components is one button press away.
Ran the full RFEM roundtrip on 2026-09-15: 3 surfaces, 8 nodes, 4 pinned
supports at level 0, ~27 s, surface results back (per mesh node: deformation
and basic internal forces), the one-way slab visibly bending at ×100.

The plate geometry is built on the canvas by the **Plate Box** script
component (source: `plate_box_component.py`) from five sliders: width,
depth, height, t_wall, t_slab (document units, metres). Two CLT walls at
x = 0 and x = width carrying a slab that spans between them, on centre-line
dimensions - the slab's mid-plane contains the wall tops, so the graph
merges the nodes (no plate joints needed). Then Translate → Support Nodes
(level 0) → Preflight → Display / Run → Results / Visualize / Attach / Save.

Two things the plate path taught, both fixed in code:

- **The slab must sit on the centre-line too.** With the slab "on top of"
  the walls its mid-plane floats half a slab thickness above the wall tops,
  the graph finds no shared nodes and the model falls into two pieces - that,
  not the upstream frame bug, was the "two parts" preflight finding.
- **RFEM's library timber material cannot carry a surface.** C24 comes with
  the 1D timber model; a plate needs a stiffness matrix. RFEM then refuses to
  calculate and says nothing in its errors table. The importer now pushes a
  second, orthotropic-2D variant of every material for the thicknesses
  (`tekton_dlubal.mappers.mapper_members.map_material(for_surfaces=True)`).

## `tekton_plates_opensees_hypar.ghx`

Two faceted hyperbolic paraboloids - tessellated into planar trimmed surfaces
(46 and 19 facets) - calculated as CLT shells. Built 2026-09-26 from
`tekton_plates_opensees.ghx` by replacing **Plate Box** with two **Hypar
Shell** script components (source: `hypar_shell_component.py`), one per
surface set. Each facet becomes one `Plate`; the shell stays one piece
because neighbouring plates end up on the *same* nodes.

```text
Surface (internalised, 46 facets) ─→ [Hypar Shell] ─┬─ model ──→ Tekton Translate ─→ Tekton Support Nodes ─→ Preflight / Run
                                                    └─ supports ────────────────────────────↗
```

Ran on OpenSees the same day: 46 plates → 118 nodes / 46 surfaces, meshed
into 5908 shells, self-weight in ~1 s, max displacement **0.73 mm**. The
second shell (19 facets) gives 40 nodes and 1.09 mm.

### What building it taught

**The outline must be pre-shifted by −t/2 along the facet normal.**
`Plate.from_outline_thickness` extrudes to *one* side: the polyline it is
given becomes `outline_a`, a **face** of the panel, and the mid-plane lands
t/2 away along that plate's own normal. The analysis model is built from
mid-planes, and every facet has a different normal, so with the raw outline
the mid-planes all drift apart and no two neighbours meet: 46 facets
translated into 46 loose pieces and 250 nodes, none shared. Shifting the
outline first puts the mid-plane back onto the original surface, where the
facets do share edges - 118 nodes, 66 of them shared by three plates, one
connected component. This is the centre-line rule of `build_plate_model.py`,
restated for arbitrary facet orientations.

**No plate joints are created, on purpose.** `PlateMiterJoint` and friends
exist to give an edge a *release*; two plates that share their nodes are
already rigidly continuous, which is what a monolithic shell wants. They
would also fail: once the outlines sit on the mid-plane the facets no longer
touch face-to-face, and `PlateConnectionSolver` returns `TOPO_UNKNOWN`.

**Concave facets are the normal case, and the viewer got them wrong.** A
tessellated hypar is full of plates whose outline steps inwards - 38 of the 46
facets here, with one or two reflex corners each. `TektonVisualize` drew them
with `Mesh.CreateFromTessellation(points, None, plane, False)`, which
triangulates a *cloud of points* and therefore returns the **convex hull**:
the notch is filled in and the plate is drawn as a spike across its own
boundary, up to 40% too large. (The flag is `allowNewVertices`, not "allow
concave".) Passing the outline as the `edges` argument fixes it - 46 of 46
facets then come out exact, with the vertex count unchanged so the result
colours still line up. Worth stressing: **only the drawing was wrong.** The
analysis model was right the whole time - meshed area equals source area to
0.00% on every facet, concave ones included.

**The solid preview fanned its end caps, and that breaks the same way.**
`TektonDisplay` draws each plate as a box: outline extruded by +-t/2, sides
as quads, caps as a triangle fan from corner 0. The fan is only valid while
the outline is convex - on this shell all 38 concave facets came out with
the wrong cap area, the notch bridged over exactly as in the deformed view.
The caps now triangulate the outline (`Mesh.CreateFromClosedPolyline`, whose
reordered vertices are mapped back by position), and all 38 are exact.

**The viewer re-triangulated the solved mesh, and that is not the same mesh.**
`TektonVisualize` drew each plate by running `Mesh.CreateFromTessellation`
over the result sample points - a 2D Delaunay of a projected cloud. On a
trimmed or concave plate that has no reason to reproduce the mesh gmsh
actually solved: measured here, 156 zero-area triangles of 1058 and 18%
below quality 0.3, where the gmsh mesh those same points came from has a
minimum quality of 0.73 and no slivers at all. The connectivity now travels
with the results (`result_set.metadata["surface_triangles"]`, triples of the
samples' `node_tag`, filled by the OpenSees reader), and the viewer rebuilds
that mesh; the tessellation stays as the fallback for a backend that sends
none. Again worth stressing: **only the drawing was affected** - the
analysis ran on the good mesh the whole time.

**Supports on a saddle are picked per boundary edge, not per vertex.** The
component takes the naked boundary edges whose *midpoint* lies below
half-height, and supports both their ends - on a hypar those are exactly the
two descending edges. A vertex rule tightened far enough to exclude the
rising edges collapses onto the two lowest corners alone, and two pinned
points let the shell rotate about the line through them: 34 km of
"deflection" before the rule was changed.

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

**Wall-to-slab coupling through a joint does not currently work**; the slab
connects through shared nodes instead (its mid-plane contains the wall tops),
which RFEM treats as a rigid line connection. The cause is upstream in compas_timber (`structural.py`): the
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
