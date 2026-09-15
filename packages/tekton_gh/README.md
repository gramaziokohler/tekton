# tekton_gh — Grasshopper components

*Status: 2026-09-15 — the roundtrip is real: the smoke test goes
Grasshopper → worker → RFEM 6 → calculate → internal forces, deformations
and reactions back onto the canvas, deformed and coloured. Verified on Windows
against a live RFEM. What is still missing is listed under "What is not real
yet". Concept: [`docs/concepts/gh-addon.md`](../../docs/concepts/gh-addon.md).*

## Why two processes

Rhino 8 ships CPython **3.9**. `dlubal-api` requires **≥ 3.10** and pulls in
grpcio, pandas and vtk. So the RFEM client fundamentally cannot run inside
Rhino — regardless of how we write our own code.

```text
┌─ Rhino 8 (CPython 3.9) ────────────────┐      ┌─ Worker (repo .venv, 3.12) ─┐
│ compas_timber (structural branch)      │      │ compas_dlubal → RFEM        │
│ compas_timber_fea  ← runs here, ✅      │ JSON │ compas_saf    → xlsx        │
│ tekton_gh (this package)               │ ───→ │                             │
│  authoring, translate, inspect          │ ←─── │ calculates, reads results   │
└────────────────────────────────────────┘      └─────────────────────────────┘
```

The process boundary is the JSON serialisation of the neutral model. No
protocol of our own — and every run leaves behind a diffable model as a side
effect, the same artefact that gets handed to engineers.

**Verified** (on 2026-08-28 in a running Rhino 8 instance):
`compas_timber_fea` imports under 3.9, `TimberToStructural.translate()`
completes (test model: 84 beams → 344 nodes, 404 members), the JSON roundtrip
works.

## Setup

**1. Create the Rhino venv.** Tekton needs `compas_timber` from the branch
`structural_graph_plates` — `compas_timber.structural` exists only there. The
official COMPAS Timber plugin ships an older version that is *not* enough.
Create a dedicated venv in Rhino and install the pinned revision into it. The
name has to match the header of every component — currently
`# venv: tekton-test`, because that env already existed on this machine. Given
an unknown name, Rhino silently creates an **empty** env, and then
compas_timber is missing; the name is not cosmetic.

**2. Make the repo path known.** Either at the `repo` input of the components,
or once as an environment variable:

```bash
export TEKTON_REPO="/path/to/tekton"
```

**3. Worker venv.** In the repo, `uv sync --extra dev` — that is the 3.12 env
`TektonRun` calls.

**3b. API key.** The Dlubal API refuses without one, also for a local RFEM.
Three ways in, in order of preference: leave `api_key` on `Tekton Backend`
empty and keep the key in the repo's `.env` (`DLUBAL_API_KEY=...`, see
`.env.example`) or in the environment (`TEKTON_API_KEY`); give `api_key` the
*path* to a file holding the key; paste the key itself (warns — it is now in
the definition).

**4. Check.** Drag the **Tekton Info** component onto the canvas. It is the
only one that produces something useful even without a working setup, and it
names exactly what is missing.

## Building the components

Step 1, plain terminal Python:

```bash
python3 _componentizer/build_metadata.py   # metadata.json + placeholder icons
```

Step 2 needs .NET (`clr`) to drive `GH_IO.dll`.

*macOS:*

```bash
bash _componentizer/componetize.bash       # via the RhinoCode CLI
```

**If that stays silent** (exit code 0, but no `componentizer.log` and no
`ghuser_build/`): open `_componentizer/build_in_rhino.py` in the Rhino Python
editor and run it. That is the same operation from inside a running Rhino
instance. On 2026-08-28 the CLI had no effect on this machine — including for
the unmodified componentizer in `lorin-gh-tools`, so it is not Tekton's fault.

*Windows:* the RhinoCode CLI refuses without a running Rhino ("Can not
determine target Rhino"). Plain CPython with `pythonnet` is enough — the
checked-in `GH_IO.dll` is net48 and loads under .NET Framework:

```powershell
uv venv %TEMP%\ghvenv --python 3.12
uv pip install --python %TEMP%\ghvenv\Scripts\python.exe pythonnet
cd _componentizer
%TEMP%\ghvenv\Scripts\python.exe componentize_cpy.py
```

Step 3, installing. macOS: `bash _componentizer/install.sh`. Windows: copy
`ghuser_build\*.ghuser` to `%APPDATA%\Grasshopper\UserObjects\tekton\`. The
target folders are

- macOS: `~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper (b45a29b1-…)/UserObjects/tekton/`
- Windows: `%APPDATA%\Grasshopper\UserObjects\tekton\`

— the subfolder keeps the Tekton components separate from the rest.
Grasshopper reads UserObjects only at startup, so a restart is required.

**Instances on the canvas do not update.** A UserObject is a template; a
component already placed in a definition keeps its embedded script. After a
rebuild, either drop the components fresh from the ribbon, or — with the
[LAMCP bridge](https://github.com/gramaziokohler/lamcp) on the canvas — let
`upgrade_components(only_categories=["Tekton"])` swap every instance in place
and carry the wires over (2026-09-15: 10 components, no wire lost).

**Editing the shared runtime** (`src/tekton_gh/*.py`) needs no rebuild: the
components put the repo path on `sys.path` and `Tekton Run` / `Tekton
Visualize` reload their module on every solve. Only `code.py` changes need the
componentizer.

The componentizer comes from `lorin-gh-tools` and is deliberately copied here
rather than referenced — the repo should stay buildable on its own. The only
change: `components/` sits one level above the tool folder.

## Layout

```text
components/<name>/        code.py + metadata.json + icon.png   (one bundle = one component)
icons/                    icon sources: <name>.svg + <name>_96.png
src/tekton_gh/            shared runtime: env.py, worker.py, rhino_io.py
_componentizer/           build tool, metadata generator, install.sh
```

Icons live in two places, and that is not an oversight: `icons/` holds the
editable SVGs, `components/<name>/icon.png` the 24px version the componentizer
expects next to `code.py`. Details in [icons/README.md](icons/README.md),
motifs and colours in [ICONS.md](ICONS.md).

The other side of the process boundary lives in `tekton_app`:
`packages/tekton_app/src/tekton_app/worker.py` — invoked as
`python -m tekton_app.worker model.json --backend rfem --out result.json`.
It can be tested independently of Grasshopper, and that is exactly what
`tests/unit/test_worker_cli.py` does.

`build_metadata.py` holds the **component table** — name, category, inputs,
outputs, descriptions. To add a component: append an entry there with a fresh
`uid`, run the script, write `code.py`.

The `uid` determines the InstanceGuid and is **stable**: a changed GUID turns
an updated component into a new one, and existing definitions lose their
wiring. Only append, never reassign.

## The components

**0 | Setup** — `Tekton Info`: diagnostics. First place to look when something
goes wrong.

**1 | Author** — what used to be possible only in Python: `Material`,
`Support`, `Load Case`, `Point Load`, `Member Load`, `Load Combination`,
`Joint Policy`, `Plate Policy`.

**2 | Translate** — `Translate` (TimberModel → StructuralModel, with an
assumptions report), `Apply Loads` (loads onto the translated model),
`Preflight` (supports? connected? plausible?).

**3 | Run** — `Backend` (selection + connection), `Run` (push, calculate,
results back — **by button only**).

**4 | Results** — `Results` (numbers per physical beam straight off the
StructuralModel: envelope per beam, samples and their parameter t on the
*beam* axis as trees, JSON record, `stale` check; with the TimberModel wired
in, the Beam objects in the same order), `Attach Results` (writes
`beam.attributes["analysis"]` via `compas_timber_fea.results`: the same
samples and envelope, plus provenance; all load cases or one), `Visualize` (deformed shape and colouring: polylines
through the deformed RFEM stations, sections swept along them as
vertex-coloured meshes, one colour per member; `quantity` is
`displacement | N | Vy | Vz | Mt | My | Mz | utilization`, `exaggeration`
scales the deformation), `Inspect` (bare debug view: system lines, nodes,
support ticks, release markers), `Display` (the analysis model as a picture:
system lines, connections highlighted - rigid links dark, couplings magenta
with a white sphere at the hinged end, shared nodes grey - supports as
engineering symbols derived from their six stiffnesses (pyramid on a plate =
pinned, rollers along the free direction, ball, block = fixed) with a label,
loads as arrows scaled by value, moments as rings, reactions in blue once
results exist; `elements` adds the solid sections, opt-in because they hide
the connections. Logic in `tekton_gh.model_view`, pure and tested).

**5 | IO** — `Save Model` / `Load Model` (JSON; also the handover format),
`To Timber` (rebuilds the TimberModel from a StructuralModel — beams exact
with their GUIDs, sections and orientation, results attached; joints are not
rebuilt because their types are not in the neutral model. For when only the
analysis model is at hand: the engineer's JSON, an earlier run).

## Smoke test

`examples/tekton_smoke_test.ghx` shows the whole chain on an example model.
Against a live RFEM 6 on 2026-09-15 (Windows): 84 beams → 344 nodes / 404
members (304 beams, 100 couplings), 4 pinned supports, 754 objects pushed in
~4 s, calculation ~25 s, back come 404 members × 11 stations with internal
forces and deformations, 344 nodal deformations, 4 reactions (Σ 5.2 kN
self-weight, C24), max deflection 17 mm, max |My| 0.19 kNm. Adjust the path
panels before opening — details in [examples/README.md](examples/README.md).

## Typical flow

```text
TimberModel ─→ Support ─→ Translate ─→ Preflight ─→ Run ─→ Results ─→ Visualize
                 ↑            ↑                      ↑
            Load Case    Joint Policy            Backend
                 ↓
          Point/Member Load ─→ Apply Loads
```

## What is not real yet

| What | State | Blocked by / next step |
|---|---|---|
| **Utilisation** | `quantity="utilization"` exists on Visualize and returns 0 | RFEM timber design add-on: add-on activation + its result table via `get_results` |
| **Joint policy from fasteners** | policy decides rigid/pinned per joint type or instance; nothing derives it from screw count/direction | a rule on the joint's fastener data — the hook (`by_type`, `by_instance`) is there |
| **Hinge side on couplings** | the hinge goes to the end where a beam terminates; for crossings (X-lap) the side is arbitrary — the 4 cm lever arm lands on one beam | split the connector at the joint face if that asymmetry ever matters |
| **Material overrides** | material is a name string, one grade for the whole model | material dataclass (`discussion/materials.md`) |
| **Support types** | supports are pinned unless authored via `Tekton Support Nodes` | neutral model |
| **Plate results** | surfaces are pushed; no surface result table is read | `STATIC_ANALYSIS_SURFACES_*` via `get_results`, same pattern as members |
| **Engineer's edits in RFEM** | every run does `delete_all` and rebuilds | BackendMap / incremental update (`discussion/roundtrip.md`) |

Done: worker CLI, result reader against live tables (forces, member and
nodal deformations, reactions), calculation-failure detection, unit contract
kN ↔ N enforced at the Dlubal boundary, one-sided coupling hinges, deformed
and coloured visualisation, results back on the beams
(`beam.attributes["analysis"]`: per load case 11 samples at the beam
parameter with N/Vy/Vz/Mt/My/Mz + displacement, envelope, provenance — 84/84
beams on the smoke test), API key from `.env`, span direction on surfaces,
icons.

## Pitfalls

**Results go stale silently.** Grasshopper holds on to old outputs — the
numbers on the canvas may describe a model that changed long ago. This is the
most dangerous failure mode of this workflow, and Grasshopper encourages it.
The countermeasure is blunt: `TektonRun` stamps the model fingerprint into
every result set, `TektonResults` compares it against the connected model and
sets `stale` plus a warning as soon as the two diverge.

**Never touch the canvas during a solve - and never assume the component
is still there afterwards.** An `AddObject` in the middle of your own
execution crashes Rhino. The documented remedy, `doc.ScheduleSolution(delay,
callback)`, moves the work out of the solve - and still crashed Rhino twice
(2026-09-10/11). The diagnosis at the time ("the Python closure gets
collected") was wrong; the real pattern showed on 2026-09-15: the crashes
happened when components were **replaced**. The old instance leaves the
document while its callback is still queued; the callback then touches the
`Attributes` of a dead component, which is a native crash with no exception.
And any Python exception escaping the delegate kills the process just as
silently.

`attach_value_list` in `tekton_gh.rhino_io` therefore has three guards:
schedule once per component instance, check that the component is still in
the document before doing anything, and let nothing escape the callback. With
those in place the drop-downs attach themselves on placement again (Material
Library, Joint Policy, Plate Policy, Backend, Support, Support Nodes, Load
Case, Results, Visualize). Verified on 2026-09-15 by scheduling a menu and
removing the component in the same UI call: Rhino survives, the queued
callback backs off, the surviving component gets its menu, a second schedule
on the same instance is refused. The `menu` buttons are gone.

**Never calculate automatically.** `TektonRun` blocks Grasshopper while it
calculates, and every run rebuilds the backend model from scratch. Hence
button-triggered, with a cache, so a canvas update does not throw the results
away.

**Units.** Rhino documents are typically mm, the neutral model works in
metres. `TektonTranslate` reads the document unit itself; anyone overriding it
should know why. A wrong value silently produces a 200-metre element.

**API key.** Not on the canvas — the `.gh` file gets passed around. Use
`TEKTON_API_KEY` in the environment instead.

**compas_timber version.** The most common setup error. If `Tekton Info` says
`compas_timber.structural` is missing, the wrong `compas_timber` is on the
path — usually the one from the official plugin.

**Rhino caches modules.** An edit to `src/tekton_gh/*.py` is invisible to a
running Rhino unless the component reloads it (Run and Visualize do). A
symptom seen on 2026-09-15: the worker was called without `--delete-all`
although the source said so — the old module was still loaded. When in
doubt, restart Rhino.

**A failed RFEM calculation does not raise.** `calculate_all` returns a
message, the result queries come back empty, and a naive reader reports
"0 members" with a straight face. The reader checks `has_results()` and
reads the errors-and-warnings table, so the solver's own text ("stiffness
matrix singular, node 39, direction Y") reaches the `log` output. If you
see it: it is mechanics, not plumbing — look at the model in RFEM.

**Units at the Dlubal boundary.** The neutral model is kN/kNm, the Dlubal
API is N/Nm. The factor lives in one place, `compas_dlubal/conventions.py`,
and applies to loads going out and results coming back. Before 2026-09-15
both directions were off by 1000 — loads arrived 1000× too small, results
1000× too large. If a number looks absurd, check the unit before the model.
