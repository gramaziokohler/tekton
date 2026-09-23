# The plate model

*Status: 2026-08-28 — design settled (see plattengraph study), implementation early*

The full design study is `../reviews/plattengraph_design_2026-08-27.md` (German,
detailed, adversarially reviewed). This is the short English version of what
was found and decided.

## Openings (2026-09-22)

`StructuralSurface.openings` holds closed rings of node ids next to
`nodes` - first-class, not subtracted into the outline. Every serious
target format carries them that way (RFEM opening object, IFC inner
boundary, SAF opening), and subtracting would destroy the plate's identity
and with it the mapping of results back onto it.

The ring vertices are ordinary model nodes, reusing an existing node where
they coincide with one. So an opening edge is the same kind of boundary an
outline edge is, and a future opening shared between two plates needs no new
mechanism.

The chain: `plate.plate_geometry.openings` (the single accessor the design
study asks for, because the plate may move them into FreeContour features)
→ translator → `StructuralSurface.openings` → gmsh as a second curve loop on
the same face → cut out of the mesh.

**One correction the numbers forced.** The openings live on `outline_a`, but
the analysis surface is the middle one - the design study notes that no
mid-plane is stored and it has to be derived by t/2. Without that shift the
opening sits half a thickness off the plate it is meant to cut, and the
meshed area came out 15.072 m² instead of 15.000 for a 4x4 plate with a 1x1
hole. The translator now derives the offset from the two outlines rather
than from the frame normal, because a plate can be built either way round.

Not yet: openings on the RFEM side, and an opening crossing a plate edge.


## How a plate is represented: one surface, untessellated

**One planar mid-plane surface per plate.** Outer polyline ring + separate
opening rings + "internal traces" (integrated lines where T-joints or ribs land
on the surface). No sub-surfaces. **No tessellation in the neutral model.**

Why: every serious target format is B-rep and **meshes itself** —

- RFEM: surface = loop of shared line objects, own mesher (default target FE
  length ~50 cm, user-controlled)
- SAF: surface member = named nodes + edges; "internal nodes are not geometry
  defining"; the *importing* software meshes
- IFC (structural analysis view): one surface + explicit curve connections

Subdividing in the neutral model would destroy plate identity (results could
no longer map back to *the plate*) and badly reimplement work the FE mesher
does better. The old GH script's UV-grid subdivision stages die for exactly
this reason.

## So how far is tessellation *our* job?

Short answer: **not at all in the neutral model; only inside mesh-based backend
adapters.** OpenSees and Karamba have no mesher — shell elements there are
pre-meshed quads, so an OpenSees/Karamba adapter must tessellate at its own
boundary (and may reuse the neutral model's mesh *hints*, never its geometry
granularity). RFEM/SAF/Abaqus adapters pass B-rep through and let the target
mesh. This split keeps one clean rule: geometry granularity in the neutral
model is *semantic* (joints, openings, traces), never *numerical* (element
size).

## How plates connect: shared border chains

The core entity of the target design is the **BorderChain**: where two plates
meet along an edge, there is **one** shared line-level entity carrying the
union of both sides' vertices, referenced by both surfaces. That maps 1:1 to
RFEM's shared-line invariant (coincident duplicate lines are a flagged model
error there) and SAF's shared named nodes. T-joints: the trace becomes an
integrated line of the host surface *and* the border of the arriving plate —
same chain on both sides *is* the adjacency.

Imprint + merge happens on the **line level**, never inside the surface.
Partial contact (offset walls, split levels) becomes an interval on the shared
carrier line: shared chain over the overlap, free edge elsewhere. N-ary
junctions (three plates on one line — platform framing) need the interval
arrangement to produce disjoint sub-chains with owner sets.

Current state is far from this: surfaces are plain node rings, no two plates
share a node, and connections were invisible to export until recently. Since
2026-08-28, connections at least export as RFEM `LineHinge` objects with a
per-edge release policy (`PlateConnectionPolicy`, default: hinged edge —
rotation about the edge axis released). That makes plate models hang together
mechanically; the chain model remains the target for doing it *right*.

## Mechanics on the connection

A plate joint law belongs **per (chain, surface side)** — RFEM's LineHinge
binds to a (line, surface) pair, SAF's `RelConnectsSurfaceEdge` similarly.
Defaults honestly hinged (screwed butt joints transfer shear, little bending);
EC5 spring stiffness from fasteners as a later stage. Eccentricities in a
three-stage policy: snap (small, in-plane, capped at ~t/2), surface
eccentricity object (systematic offsets like sheathing over ribs), rigid link
line-to-line (everything else — the proto exists in dlubal-api 2.13.8,
verified). Platform framing explicitly must *not* be snapped — the lever arm
is real.

## Orientation and orthotropy

Every surface carries a **span direction** (`span_direction`, implemented):
frame.x of the plate, i.e. the geometric main axis. This is the reference
direction any orthotropic material needs — and RFEM result quantities (m_x…)
follow the surface axes, so without pinning it, plate results are
uninterpretable. Honest caveat: it is a geometric axis, not a measured grain
direction; compas_timber has **no layup data** (no layers, no material — only
total thickness), so an actual orthotropic stiffness (CLT D-matrix incl.
rolling shear) is currently impossible to derive. The `ThicknessAssembly`
(UNIFORM | LAYERED) in the target design is where layup will live once the
data exists.

## Small conventions worth pinning

- Mid-plane = pairwise mean of outline_a/b (valid thanks to compas_timber's
  1:1 vertex invariant); the plate's own frame sits on face a, so analysis
  plane = frame + t/2.
- Openings are first-class in compas_timber and must stay first-class through
  export (RFEM `Opening` objects, SAF opening sheets) — today they are
  silently lost.
- Z axis: neutral model is Z-up (COMPAS); RFEM is Z-down — conversion at the
  Dlubal boundary only. Whether the current Z-negation mirrors chiral models
  is still unverified (needs one live test).

## Open

- Implement the chain model (migration order in the plattengraph doc, part 4;
  increments 1–3 are the substance).
- Joint-driven reconnection in compas_timber's `structural.py` — replaces the
  longest-edge heuristic (which fails on T-landings and is order-dependent).
- Openings end-to-end.
- Beam↔plate connections (no detection category exists at all today).
- Panels (wall assemblies) have no structural idealisation — `IdealizationPolicy`
  per panel: single surface with layup / ribs+skin / exploded layers.
- Helpful existing utilities flagged in discussion:
  `apply_edge_extensions` (plate_geometry.py) for edge-plane manipulation,
  `get_segment_range_on_polyline` (geometry.py) for interval clipping.

## Sources

- `../reviews/plattengraph_design_2026-08-27.md` — full study; proto claims marked
  VERIFIZIERT were checked against the pinned dlubal-api 2.13.8 wheel
- RFEM 6 documentation on surfaces/lines/integrated objects; saf.guide on
  StructuralSurfaceMember and edge connections
