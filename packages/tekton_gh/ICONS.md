# Icon briefing — Tekton components

Template for designing the icons of the 25 Grasshopper components. All 25 are
drawn and installed; the motifs below are the brief they were made against,
and the reference when one is reworked.

## House style (from `lorin-gh-tools/gh-icons`)

```
Canvas        24 × 24, viewBox "0 0 24 24", transparent background
Stroke        #26272A, stroke-width 1.8, linecap/linejoin round, fill none
Accent        one colour per category, used sparingly — it carries the message
Nodes         circles r=1.5 (normal) / r=1.8–2.1 (emphasised), filled, stroke none
Deliverable   <name>.svg + <name>_24.png + <name>_96.png
```

Reference SVG (`mesh-topology.svg`) as a pattern for structure and stroke work:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"
     fill="none" stroke="#26272A" stroke-width="1.8"
     stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 13 L5 9 M12 13 L20 7"/>
    <circle cx="5" cy="9" r="1.5" fill="#26272A" stroke="none"/>
    <path d="M12 13 L13 8.5" stroke="#98d350"/>
</svg>
```

**Accent colours already in use** (do not reuse them, so Tekton stays
distinguishable): `#505fd3` Basic Geometry, `#d35052` Architecture/Terrain,
`#98d350` Analysis, `#c650d3` Diverse, `#a5a9ae` General Tools.

## Colour proposal for Tekton

Tekton is a ribbon category of its own with six groups. Proposal, inside the
existing system (`…d3` saturation, 50/100 value) and in a corner of the colour
wheel that is still free — cyan/turquoise:

| Group | Accent | Reasoning |
|---|---|---|
| 0 \| Setup | `#a5a9ae` grey | diagnostics, no engineering statement — like General Tools |
| 1 \| Author | `#50a9d3` light blue | inputs the designer sets |
| 2 \| Translate | `#50d3c6` turquoise | the translation itself, the heart of it |
| 3 \| Run | `#d3a850` orange | action with outside effect, handle with care |
| 4 \| Results | `#8f50d3` violet | what flows back from the calculation |
| 5 \| IO | `#7a8288` dark grey | file in/out, serving |

Alternative, if it should be simpler: **one** Tekton colour (`#50d3c6`) for
all of them, with the groups told apart only by the motif.

## A consistent visual language

Tekton translates **physical elements** into a **mechanical analysis model**.
That duality should run through everything:

- **Element** = rectangle/beam with width (thick outline)
- **Analysis model** = thin system line with nodes
- **Node** = filled circle
- **Support** = triangle or hatching under a node
- **Release** = small open circle in the member (standard structural symbol)

Use structural symbols wherever possible, the way engineers know them — the
audience reads them without explanation.

---

# The 25 components

## 0 | Setup — grey `#a5a9ae`

### Tekton Info (`TInfo`)
Diagnoses the environment: Python version, compas_timber version, is the repo
found, is there a worker venv. First place to look when something is red.
*Motif:* a tick/cross list or an "i" in a circle; alternatively a stethoscope
idea — something that says "check the state", not "display information".

### Tekton Upgrade (`TUpgrade`)
Brings every Tekton component in the definition up to date with one button
press: each is swapped for the current version in place, keeping its wires and
nickname. A placed component otherwise keeps the script it was placed with, so
this is what you press after a Tekton update. The report names any wire it
could not carry over.
*Motif:* two component boxes swapping places, the exchange arrows between them
in the Setup grey. The statement is the swap, not the single box.

---

## 1 | Author — light blue `#50a9d3`

What the designer gives the model in the way of engineering knowledge. The
common bracket: **something is attached to an element.**

### Tekton Material (`TMat`)
Pick a material (C24, GL24h …). Today a name that RFEM resolves against its
own library.
*Motif:* beam cross-section with wood grain/growth rings; accent on the grain.

### Tekton Material Library (`TMatLib`)
Pick a grade from the library. Hangs a drop-down on itself when placed, so
nobody has to type "GL24h" correctly; without a selection it lists what is
available, with the property values.
*Motif:* stacked material cards, the front one carrying the grain in the
accent — a shelf you reach into. Reads as a sibling of Tekton Material, not a
duplicate: that one is about overriding single values, this one about
choosing.

### Tekton Support (`TSup`)
Mark support points on beams.
*Motif:* a horizontal beam with the classic support triangle beneath it in the
accent colour. The clearest symbol in the whole set — it should be readable
instantly.

### Tekton Load Case (`TCase`)
Define a load case (self-weight, imposed, snow, wind). A container that loads
refer to.
*Motif:* several stacked layers/cards, one of them picked out in the accent
colour — "one of several cases".

### Tekton Point Load (`TPLoad`)
Point load at a location, force in kN.
*Motif:* a single thick downward arrow onto a point, arrow in the accent
colour.

### Tekton Member Load (`TMLoad`)
Line load on beams, kN/m.
*Motif:* a row of equal-length downward arrows above a beam, with the
connecting top line (the standard depiction of a uniform load).

### Tekton Load Combination (`TComb`)
Combine load cases with partial safety factors.
*Motif:* two or three arrows converging into one; or a Σ gesture. The
difference from Load Case has to be clear: here you **compute**, there you
**name**.

### Tekton Joint Policy (`TPolicy`)
The rule for how a timber joint is idealised mechanically: pinned, rigid or
spring. An engineering decision, not geometry.
*Motif:* two members meeting, with the open circle of the release symbol at
the meeting point in the accent colour. Ideally it should be visible that this
is a *choice* — for instance two variants side by side.

### Tekton Plate Policy (`TPlatePol`)
How plate edges are coupled (hinged/continuous), plus the span direction. The
latter is not optional decoration: plate materials are orthotropic, and RFEM's
m_x follows the surface axes — without a defined direction the moments cannot
be interpreted.
*Motif:* two plates meeting in plan view, the joint emphasised, plus a
direction arrow for the span direction. The arrow is the actual statement —
put it in the accent colour, keep the joint dark.

---

## 2 | Translate — turquoise `#50d3c6`

The core: elements become an analysis model.

### Tekton Translate (`TTrans`)
TimberModel → neutral analysis model. Produces system lines, nodes,
cross-sections, releases, supports, plus an assumptions report.
*Motif:* **the key image of the set.** On the left a beam with width (thick
outline), on the right the same geometry as a thin system line with nodes, an
arrow in between. Ideally as one figure that switches from element to line
halfway across.

### Tekton Apply Loads (`TApply`)
Applies the authored loads to the translated model (point → node, element GUID
→ all members it produced).
*Motif:* a system line with nodes, load arrows snapping onto it; accent on the
arrows. The difference from Point/Member Load: there the load is *defined*,
here it is *assigned*.

### Tekton Support Nodes (`TSupN`)
Supports placed straight onto nodes of the analysis model, selected by a plane
or by proximity to points. Needed for plates: the translator reads
`support_points` off beams only, so a plate model would reach analysis
unsupported — a mechanism. Runs after Translate, because the nodes exist only
from then on.
*Motif:* the support triangle from Tekton Support, but hanging off an
emphasised node on a system line rather than sitting under a beam. The pair
reads as "same idea, other end of the pipeline" — Support authors on the
element, this one lands on the model.

### Tekton Preflight (`TCheck`)
Checks before calculating: supports present? model connected? references
valid? Stops a floating system from being calculated without comment.
*Motif:* a system line with a warning triangle or a check mark; accent on the
finding. The statement is "check before starting", not "error".

---

## 3 | Run — orange `#d3a850`

Action with outside effect — the colour should make you pause.

### Tekton Backend (`TBackend`)
Pick a backend (RFEM/RSTAB/SAF) and bundle the connection data.
*Motif:* a plug/port or a switch with two or three destinations. Something
that says "pick a target and connect".

### Tekton Run (`TRun`)
Model to the backend, calculate, results back. Runs in a separate process.
**By button only** — the run blocks Grasshopper and rebuilds the backend model
from scratch.
*Motif:* a play triangle combined with the cycle arrow (there and back). It
has to be recognisable as "this is the trigger".

---

## 4 | Results — violet `#8f50d3`

What comes back from the calculation.

### Tekton Results (`TRes`)
Results per physical beam: envelope values and sample points along the axis.
Warns when the numbers belong to an older state of the model.
*Motif:* a beam with a moment diagram/curve above it; accent on the extreme
value. Structural diagram language.

### Tekton Attach Results (`TAttach`)
Writes the results back onto the timber model, with their provenance.
*Motif:* an arrow pointing from a curve/number back onto a beam — the
direction "back onto the element" is the statement.

### Tekton Visualize (`TViz`)
Colours elements by a result value, with a legend. Hard red above the upper
bound.
*Motif:* a beam in a colour gradient (green→yellow→red) — here, as an
exception, more colour than usual may go into the icon, because that is
exactly the function.

### Tekton Inspect (`TInspect`)
Shows the analysis model itself: system lines, nodes, support symbols, release
markers. For checking the idealisation before calculating.
*Motif:* a magnifier over a system-line truss with visible nodes. The
difference from Results: here the **system**, there the **numbers**.

### Tekton Display (`TDisplay`)
The analysis model as a picture: connections, support symbols by condition,
load arrows, reactions; member geometry semi-transparent on a toggle. The
presentation view - Inspect is the debug view.
*Motif:* a beam on two pinned supports (triangles on base lines) with a load
arrow from above - the textbook sketch, in the Results accent.

---

## 5 | IO — dark grey `#7a8288`

### Tekton Save Model (`TSave`)
Writes the neutral model as JSON — also the handover format for engineers,
assumptions report included.
*Motif:* a system-line figure flowing into a document/file; arrow downward/in.

### Tekton To Timber (`TToTimber`)
Rebuilds the TimberModel from a StructuralModel: system line in, beam out,
results attached. For when only the analysis model is at hand.
*Motif:* a system line with an arrow down into a beam box (the reverse of
Translate's motif).

### Tekton Load Model (`TLoad`)
Reads a saved model, results included, back onto the canvas.
*Motif:* the mirror image of Save — arrow out of the document. The two should
be recognisable as a pair.

---

## Notes on execution

- **24px is the real size.** Everything has to stay readable there: at most
  two or three visual elements, no thin details, no text.
- **Make the pairs visible:** Save/Load, Point Load/Member Load, Joint
  Policy/Plate Policy, Results/Inspect, Translate/To Timber (the arrow turns
  round), Material/Material Library (override vs. choose), Support/Support
  Nodes (on the element vs. on the node). Same base figure, one element
  mirrored or swapped.
- **The accent carries the message.** In the reference SVG exactly the new
  thing is coloured, the context stays dark. That keeps the meaning readable
  in greyscale too.
- **Not every icon needs to invent something.** Where an established
  structural symbol exists (support, release, uniform load), that is the right
  choice.

## Where the files go

Finished icons go here, then rebuild:

```
components/<bundle>/icon.png     # 24px, replaces the placeholder
```

Bundle names: `tekton_info`, `tekton_upgrade`, `tekton_material`,
`tekton_material_library`, `tekton_support`, `tekton_load_case`,
`tekton_point_load`, `tekton_member_load`, `tekton_combination`,
`tekton_joint_policy`, `tekton_plate_policy`, `tekton_translate`,
`tekton_support_nodes`, `tekton_apply_loads`, `tekton_preflight`,
`tekton_backend`, `tekton_run`, `tekton_results`, `tekton_attach_results`,
`tekton_visualize`, `tekton_inspect`, `tekton_display`, `tekton_save_model`,
`tekton_to_timber`, `tekton_load_model`.

All 25 carry real icons. `icons/_todo/` keeps only the magenta placeholder
itself, for the next component that arrives without one.

Then:

```bash
python3 _componentizer/build_metadata.py   # leaves an existing icon.png alone
# run the componentizer (see README), then:
bash _componentizer/install.sh
```

`build_metadata.py` does **not** overwrite an existing `icon.png` — it only
creates what is missing. Real icons are therefore safe.
