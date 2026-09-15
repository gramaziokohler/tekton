# How the target softwares want things

*Status: 2026-09-15 — RFEM/SAF columns well-researched; OpenSees column spiked
against openseespy 3.8 (see opensees-backend.md); Abaqus from general
knowledge, marked where unverified*

One table, softwares as columns, topics as rows. This is the document to
extend whenever we learn how another system does something. Legend:
✅ verified (code/proto/spec checked) · ◐ reasonably sure · ? to verify · — not applicable.

| Topic | RFEM 6 (gRPC) | RSTAB 9 | SAF (xlsx) | OpenSees | Abaqus |
|---|---|---|---|---|---|
| **Exchange mode** | ✅ live API, batched object push | ✅ same API family | ✅ one-way file | ✅ script (openseespy, pip), no file format | ◐ input deck / scripting (or via COMPAS FEA2) |
| **Geometry paradigm** | ✅ B-rep: nodes, lines, surfaces | ✅ members only, **no surfaces** | ✅ B-rep, named shared nodes | ✅ none — nodes + elements only | ◐ parts/assembly B-rep, but scripted models often direct mesh |
| **Who meshes** | ✅ RFEM (target FE length, default ~0.5 m) | — (no plates) | ✅ the importing software | ✅ **we do** — pre-meshed tris/quads; built-in `mesh` is PFEM-only | ◐ Abaqus meshes, scriptable |
| **Member** | ✅ node pair + cross-section ref | ✅ same | ✅ CurveMember, begin/end node | ✅ elasticBeamColumn: node pair + A,E,G,J,Iy,Iz as numbers (J not in neutral model) | ◐ wire + beam section assignment |
| **Member orientation** | ✅ β rotation angle vs. default orientation, Z-down space | ✅ same | ✅ LCS "y by vector" (vector in file) — *not* a rotation angle | ✅ geomTransf with vecxz = x × local y | ◐ beam section orientation (n1 direction) |
| **End releases** | ✅ MemberHinge object (per-DOF stiffness, inf=rigid, 0=free), referenced per member end | ✅ same family | ✅ RelConnectsStructuralMember sheet (hinge) | ✅ `-releasey/-releasez` codes for bending; zeroLength springs + equalDOF between duplicate nodes for the rest | ◐ connector elements / released DOFs at connection |
| **Rigid coupling** | ✅ member type RIGID; coupling hinge-hinge (type 24); RigidLink incl. LINE_TO_LINE | ✅ member types | ✅ RelConnectsRigidLink / RigidMember | ✅ rigidLink works but reports no reactions → stiff beam | ◐ MPC / coupling constraints |
| **Plate** | ✅ Surface = loop of shared **line objects**; coincident duplicate lines = flagged error | — | ✅ SurfaceMember: node ring + edges; internal nodes not geometry-defining | ✅ ShellDKGT/DKGQ/MITC4 on a mesh we build; `-surfaceLoad` ignored → nodal loads | ◐ shell part + section; **composite layup native** (good for CLT) |
| **Plate edge joint** | ✅ LineHinge per (line, surface); slab-wall variant exists | — | ✅ RelConnectsSurfaceEdge (rotations free/rigid/flexible; translations always transferred — SAF-side restriction) | ◐ duplicate node rows + springs (our construction) | ? connector/contact, to check |
| **Openings** | ✅ Opening object (boundary lines + surfaces) | — | ✅ SurfaceMemberOpening sheet | ◐ holes in our mesh | ◐ geometry cut |
| **Materials** | ✅ library, resolved by name string ("C24 \| EN 338:2016-04") | ✅ same | ✅ name + physical properties in sheet | ✅ **no library** — numbers only | ◐ no library — engineering constants; orthotropic/lamina native |
| **Sections** | ✅ parametric by name string ("R_M1 w/h") | ✅ same | ✅ parametric shape + parameters + A/Iy/Iz | ✅ A/I on the element, or `section Elastic` for forceBeamColumn | ◐ profile objects |
| **Loads** | ✅ NodalLoad (component vector), MemberLoad (one direction per object), SurfaceLoad, free loads, load wizards | ✅ minus surface loads | ✅ PointAction/CurveAction/SurfaceAction sheets | ✅ pattern + timeSeries, nodal & eleLoad (local axes, partial ok); no self-weight | ◐ steps + loads |
| **Load cases & combinations** | ✅ LoadCase with action category; combination wizard (EC0) | ✅ same | ✅ LoadCase + LoadGroup + Combination sheets, no wizard | ✅ manual — one pattern per case, superpose or factor | ◐ steps; combinations manual/scripted |
| **Supports** | ✅ NodalSupport (per-DOF stiffness), LineSupport | ✅ nodal | ✅ PointSupport (enums Rigid/Free/Flexible + stiffness), edge supports | ✅ fix / zeroLength springs | ◐ BCs on regions |
| **Units** | ✅ SI base units over the API | ✅ same | ✅ metric sheets, units in column headers | ✅ unitless — kN, m go in as they are | ◐ unitless — same |
| **Vertical axis** | ✅ global Z **down** (API side) | ✅ same | ✅ Z **up** | ✅ user convention — Z-up like the neutral model | ◐ user convention |
| **Results access** | ✅ get_result_table → DataFrame; timber design add-on has utilization tables (? untested) | ◐ same family | ✅ spec has result sheets (? which importers write them) | ✅ nodeDisp/nodeReaction/eleResponse/sectionForce in-process; signs to calibrate | ◐ ODB, scripted queries |
| **Stable foreign IDs** | ✅ id_for_export_import string field on objects | ? probably same | ✅ Id columns are GUIDs; Parent ID groups segments | ✅ our numbering *is* the model | ◐ set/instance names |

## What the table tells us

- **The neutral model must be the superset.** Everything RFEM resolves by name
  (materials, sections), OpenSees needs as numbers. So the neutral model
  carries the numbers, and name-resolution is a Dlubal-adapter convenience —
  not the other way around. (This is the whole argument in materials.md.)
- **Two backend families.** B-rep backends (RFEM, SAF, Abaqus-ish) take our
  geometry and mesh themselves; mesh backends (OpenSees, Karamba) need an
  adapter that tessellates. The neutral model stays B-rep; see plate-model.md.
- **Releases translate everywhere, differently.** Per-DOF stiffness
  (inf/0/spring) is expressible in all five columns — as hinge objects, sheet
  enums, or spring elements. The neutral convention holds up.
- **Orientation is the classic silent-corruption spot.** Rotation angle
  (RFEM, against a Z-down default) vs. direction vector (SAF, OpenSees) —
  storing the *vector* neutrally and converting per backend was the right
  call; the SAF mirror bug came from leaking the RFEM convention.
- **RSTAB is a degradation target.** No surfaces: a plate model must either be
  refused loudly or converted to a grillage — explicit decision, never a
  silent drop.

## To verify (each is a small, bounded task)

- RFEM timber design add-on result tables via get_result_table (utilization —
  the designer-loop headline number).
- SAF result sheets: which consumers actually write/read them?
- Chirality of our Z-down conversion (one live test, asymmetric frame).
- ~~OpenSees column~~ spiked 2026-09-15, see opensees-backend.md. Abaqus column
  still from experience — spike a 10-line model before building an adapter.
- ~~Whether COMPAS FEA2 is the pragmatic route to OpenSees~~ — no (see
  opensees-backend.md: tcl + separate binary, releases unimplemented, no line
  loads). Still open for Abaqus.

## Sources

- RFEM/RSTAB: proto inspection of pinned dlubal-api 2.13.8 (claims marked ✅),
  Dlubal online docs
- SAF: saf.guide specification (sheet/enum names verified during export fixes)
- OpenSees: `tests/spike_opensees.py` against openseespy 3.8.0.0 (claims
  marked ✅), openseespydoc / opensees.github.io; Abaqus: scripting manual,
  from general knowledge, marked ◐
