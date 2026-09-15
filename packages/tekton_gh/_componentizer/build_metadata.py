"""Generates metadata.json + placeholder icons for all Tekton components.

Why generated and not hand-written: the componentizer's metadata.json is very
verbose (about 12 lines per parameter). With 14 components a table plus a
generator is easier to read, and it keeps the conventions (GUID assignment,
category, ordering) consistent automatically.

Run it with plain Python 3, no Rhino needed::

    python3 _componentizer/build_metadata.py

Then build the components::

    bash _componentizer/componetize.bash
"""

import json
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENTS_DIR = os.path.join(os.path.dirname(HERE), "components")

CATEGORY = "Tekton"

# Every component has a fixed number ("uid") that the InstanceGuid is built
# from. A changed GUID turns an updated component into a *new* one: existing
# definitions then lose their wiring. That is why the numbers are explicit and
# not derived from the list position - reordering is safe, reassigning never is.
SUB_SETUP = "0 | Setup"
SUB_AUTHOR = "1 | Author"
SUB_TRANSLATE = "2 | Translate"
SUB_RUN = "3 | Run"
SUB_RESULTS = "4 | Results"
SUB_IO = "5 | IO"


def p(name, hint="ghdoc", access="item", optional=True, desc="", nickname=None):
    """Input parameter definition (shorthand)."""
    return {
        "name": name,
        "nickname": nickname or name,
        "description": desc,
        "optional": optional,
        "allowTreeAccess": True,
        "showTypeHints": True,
        "scriptParamAccess": access,
        "wireDisplay": "default",
        "sourceCount": 0,
        "typeHintID": hint,
        "reverse": False,
        "simplify": False,
    }


def o(name, desc="", nickname=None):
    """Output parameter definition (shorthand)."""
    return {
        "name": name,
        "nickname": nickname or name,
        "description": desc,
        "optional": False,
        "sourceCount": 0,
        "graft": False,
    }


# --------------------------------------------------------------------------
# The component table. Order here = order in the GH menu.
# --------------------------------------------------------------------------

COMPONENTS = [
    # ---------------- Setup ----------------
    dict(
        folder="tekton_info",
        uid=1,
        name="Tekton Info",
        nickname="TInfo",
        sub=SUB_SETUP,
        description=(
            "Status report of the Tekton environment: Python version, compas_timber version, "
            "whether compas_timber.structural is present, whether the repo and the worker venv "
            "are found. First place to look when a component turns red."
        ),
        inputs=[
            p("repo", "str", desc="Path to the Tekton monorepo. Empty = environment variable TEKTON_REPO."),
        ],
        outputs=[o("report", "Diagnostic lines"), o("ok", "True when everything needed is there")],
    ),
    # ---------------- Author ----------------
    dict(
        folder="tekton_material",
        uid=2,
        name="Tekton Material",
        nickname="TMat",
        sub=SUB_AUTHOR,
        description=(
            "Pick the material for the analysis model. Today the neutral model carries only "
            "a name string that RFEM resolves against its own library. Once the material "
            "dataclass with presets exists (see discussion/materials.md), this component "
            "will return a full material with overrides."
        ),
        inputs=[
            p("grade", "str", desc="Grade, e.g. 'C24' or 'GL24h'."),
            p("E0_mean", "float", desc="Optional override for E0,mean [N/mm2]."),
            p("density", "float", desc="Optional override for density [kg/m3]."),
        ],
        outputs=[o("material", "Material for TektonTranslate"), o("info", "What was actually set")],
    ),
    dict(
        folder="tekton_material_library",
        uid=21,
        name="Tekton Material Library",
        nickname="TMatLib",
        sub=SUB_AUTHOR,
        description=(
            "Pick a material from the library. On placement it attaches its own drop-down "
            "with all grades - no typing, no typos. Without a selection it lists what is "
            "available, along with the property values."
        ),
        inputs=[
            p("grade", "str", desc="Grade. Empty = only list what is available."),
        ],
        outputs=[
            o("material", "Material for TektonTranslate"),
            o("grades", "All available grades"),
            o("properties", "Property values of the selection"),
        ],
    ),
    dict(
        folder="tekton_support",
        uid=3,
        name="Tekton Support",
        nickname="TSup",
        sub=SUB_AUTHOR,
        description=(
            "Mark support points on beams. Writes beam.attributes['support_points'] - the only "
            "channel the translator reads today. The points have to lie on the beam axis "
            "(tolerance 1e-4 in model units)."
        ),
        inputs=[
            p("model", desc="TimberModel (COMPAS Timber).", optional=False),
            p("points", "point", access="list", desc="Support points."),
            p("support_type", "str", desc="'pinned' | 'fixed' | 'roller'. Default: pinned."),
            p("tolerance", "float", desc="Search radius around the beam axis. Default 1e-4 (model units)."),
        ],
        outputs=[
            o("model", "TimberModel with support attributes set"),
            o("found", "Points that were assigned"),
            o("missed", "Points with no beam within reach - check these!"),
        ],
    ),
    dict(
        folder="tekton_load_case",
        uid=4,
        name="Tekton Load Case",
        nickname="TCase",
        sub=SUB_AUTHOR,
        description=(
            "Define a load case (self-weight, imposed, snow, wind). Load cases are the "
            "containers that loads and combinations refer to."
        ),
        inputs=[
            p("name", "str", desc="Name of the load case."),
            p("category", "str", desc="PERMANENT | VARIABLE | SNOW | WIND."),
            p("self_weight", "bool", desc="Apply self-weight automatically."),
            p("id", "int", desc="Optional fixed ID. Empty = numbered consecutively."),
        ],
        outputs=[o("load_case", "Load case for Translate/Loads")],
    ),
    dict(
        folder="tekton_point_load",
        uid=5,
        name="Tekton Point Load",
        nickname="TPLoad",
        sub=SUB_AUTHOR,
        description=(
            "Point load at a location. On application it is assigned to the nearest node of "
            "the analysis model - so the assignment happens after translating, because only "
            "then do nodes exist."
        ),
        inputs=[
            p("point", "point", desc="Point of application."),
            p("force", "vector", desc="Force [kN]."),
            p("moment", "vector", desc="Moment [kNm]. Optional."),
            p("load_case", desc="Load case from TektonLoadCase."),
        ],
        outputs=[o("load", "Point load for TektonApplyLoads")],
    ),
    dict(
        folder="tekton_member_load",
        uid=6,
        name="Tekton Member Load",
        nickname="TMLoad",
        sub=SUB_AUTHOR,
        description=(
            "Line load on beams. The assignment goes through the element GUID, not through "
            "member numbers - one physical beam is split into several members when it is "
            "idealised, and the load has to reach all of them."
        ),
        inputs=[
            p("beams", access="list", desc="Beams (COMPAS Timber) or their GUIDs."),
            p("force", "vector", desc="Line load [kN/m]."),
            p("load_case", desc="Load case from TektonLoadCase."),
            p("start", "float", desc="Relative start 0..1. Default 0."),
            p("end", "float", desc="Relative end 0..1. Default 1."),
        ],
        outputs=[o("load", "Line load for TektonApplyLoads")],
    ),
    dict(
        folder="tekton_combination",
        uid=7,
        name="Tekton Load Combination",
        nickname="TComb",
        sub=SUB_AUTHOR,
        description=(
            "Load combination from load cases and partial safety factors. "
            "Later: an EC0 generator instead of doing this by hand."
        ),
        inputs=[
            p("name", "str", desc="Name, e.g. 'ULS 1'."),
            p("load_cases", access="list", desc="Load cases."),
            p("factors", "float", access="list", desc="Factors, parallel to load_cases."),
            p("combination_type", "str", desc="ULS | SLS. Default ULS."),
        ],
        outputs=[o("combination", "Combination for TektonApplyLoads")],
    ),
    dict(
        folder="tekton_joint_policy",
        uid=8,
        name="Tekton Joint Policy",
        nickname="TPolicy",
        sub=SUB_AUTHOR,
        description=(
            "Rule for how timber joints are idealised mechanically (pinned, rigid, spring). "
            "That is an engineering decision, not geometry - so it is explicit, overridable "
            "and documented in the assumptions report."
        ),
        inputs=[
            p("preset", "str", desc="'conservative' (everything pinned) | 'rigid' | 'catalogue'."),
            p("joint_types", "str", access="list", desc="Joint types that should deviate."),
            p("releases", "str", access="list", desc="Matching: 'rigid'|'pinned'|'spherical', parallel to joint_types."),
        ],
        outputs=[o("policy", "JointPolicy for TektonTranslate"), o("info", "Resolved rules")],
    ),
    dict(
        folder="tekton_plate_policy",
        uid=9,
        name="Tekton Plate Policy",
        nickname="TPlatePol",
        sub=SUB_AUTHOR,
        description=(
            "How plate edges are coupled to each other (hinged edge vs. continuous). "
            "The counterpart to the joint policy for the plate path."
        ),
        inputs=[
            p("preset", "str", desc="'hinged' (default) | 'continuous'."),
            p("span_direction", "vector", desc="Span direction. Not optional for timber - orthotropy."),
        ],
        outputs=[o("policy", "PlateConnectionPolicy for TektonTranslate")],
    ),
    # ---------------- Translate ----------------
    dict(
        folder="tekton_apply_loads",
        uid=20,
        name="Tekton Apply Loads",
        nickname="TApply",
        sub=SUB_TRANSLATE,
        description=(
            "Applies the authored loads to the translated analysis model. Has to run AFTER "
            "TektonTranslate: point loads need nodes, line loads need the members a beam was "
            "split into. Neither exists before translating."
        ),
        inputs=[
            p("structural", desc="StructuralModel from TektonTranslate.", optional=False),
            p("loads", access="list", desc="From TektonPointLoad / TektonMemberLoad."),
            p("combinations", access="list", desc="From TektonLoadCombination."),
            p("tolerance", "float", desc="Search radius point load -> node [m]. Default 0.01."),
        ],
        outputs=[
            o("structural", "StructuralModel with loads"),
            o("report", "What was assigned - and what was not"),
        ],
    ),
    dict(
        folder="tekton_support_nodes",
        uid=22,
        name="Tekton Support Nodes",
        nickname="TSupN",
        sub=SUB_TRANSLATE,
        description=(
            "Add supports directly to nodes of the analysis model, selected by a plane or by "
            "proximity to points. Needed for plates: the translator reads support_points off "
            "beams only, so a plate model reaches analysis unsupported - a mechanism. Runs "
            "after Translate, because nodes only exist from then on."
        ),
        inputs=[
            p("structural", desc="StructuralModel from TektonTranslate.", optional=False),
            p("points", "point", access="list", desc="Support locations. Empty = use the level below."),
            p("level", "float", desc="Alternative: every node at this z (document units)."),
            p("support_type", "str", desc="'pinned' (default) | 'fixed' | 'roller'."),
            p("tolerance", "float", desc="Match radius in document units. Default 1.0."),
        ],
        outputs=[
            o("structural", "StructuralModel with supports"),
            o("nodes", "Supported node points"),
            o("report", "What was matched, and what was not"),
        ],
    ),
    dict(
        folder="tekton_translate",
        uid=10,
        name="Tekton Translate",
        nickname="TTrans",
        sub=SUB_TRANSLATE,
        description=(
            "The core of the bridge: TimberModel -> neutral StructuralModel. Produces system "
            "lines, nodes, cross-sections, releases, supports. The 'report' output lists every "
            "assumption made - that is not debug output, it is what the engineer will argue "
            "about later."
        ),
        inputs=[
            p("model", desc="TimberModel (COMPAS Timber).", optional=False),
            p("material", desc="From TektonMaterial. Empty = C24."),
            p("joint_policy", desc="From TektonJointPolicy. Empty = conservative (pinned)."),
            p("plate_policy", desc="From TektonPlatePolicy."),
            p("load_cases", access="list", desc="From TektonLoadCase. Empty = self-weight only."),
            p("units", "str", desc="Units of the timber model. Empty = Rhino document unit."),
            p("repo", "str", desc="Path to the Tekton monorepo (see TektonInfo)."),
        ],
        outputs=[
            o("structural", "Neutral StructuralModel"),
            o("report", "Assumptions report - read it!"),
            o("preview", "System lines for checking"),
        ],
    ),
    dict(
        folder="tekton_preflight",
        uid=11,
        name="Tekton Preflight",
        nickname="TCheck",
        sub=SUB_TRANSLATE,
        description=(
            "Checks the analysis model before calculating: supports present? model connected? "
            "cross-sections plausible? Otherwise a model without supports goes into the "
            "calculation without comment and returns nonsense or a solver abort."
        ),
        inputs=[
            p("structural", desc="StructuralModel from TektonTranslate.", optional=False),
            p("strict", "bool", desc="True = findings raise an error instead of a warning."),
        ],
        outputs=[
            o("ok", "True when nothing critical was found"),
            o("issues", "Findings in plain language"),
        ],
    ),
    # ---------------- Run ----------------
    dict(
        folder="tekton_backend",
        uid=12,
        name="Tekton Backend",
        nickname="TBackend",
        sub=SUB_RUN,
        description=(
            "Bundles the backend and its connection data. The API key does NOT belong in the "
            "GH file - that file gets emailed around. Leave it empty (the worker reads "
            "TEKTON_API_KEY / DLUBAL_API_KEY or the repo's .env) or pass the path to a file "
            "holding the key."
        ),
        inputs=[
            p("backend", "str", desc="'rfem' | 'rstab' | 'saf'."),
            p("api_key", "str", desc="Empty: environment or repo .env. A file path: key is read from it. Anything else: the key itself (warns)."),
            p("repo", "str", desc="Path to the monorepo (that is where the worker venv lives)."),
            p("filepath", "str", desc="Only for 'saf': target path of the xlsx file."),
        ],
        outputs=[o("backend", "Backend configuration for TektonRun")],
    ),
    dict(
        folder="tekton_run",
        uid=13,
        name="Tekton Run",
        nickname="TRun",
        sub=SUB_RUN,
        description=(
            "Send the model to the backend, calculate, fetch the results back. "
            "Runs in a separate process (backends need Python >= 3.10). "
            "Trigger by button ONLY - every run rebuilds the RFEM model from scratch and "
            "blocks Grasshopper while it calculates."
        ),
        inputs=[
            p("structural", desc="StructuralModel from TektonTranslate.", optional=False),
            p("backend", desc="From TektonBackend.", optional=False),
            p("load_cases", "int", access="list", desc="Load cases whose results are read. Empty = all."),
            p("model_name", "str", desc="Name of the model in the backend."),
            p("calculate", "bool", desc="False = only hand over, do not calculate (handoff)."),
            p("run", "bool", desc="Button. Triggers the run.", optional=False),
        ],
        outputs=[
            o("structural", "Model with results"),
            o("log", "Worker output"),
            o("stamp", "Fingerprint + timestamp of the run"),
        ],
    ),
    # ---------------- Results ----------------
    dict(
        folder="tekton_results",
        uid=14,
        name="Tekton Results",
        nickname="TRes",
        sub=SUB_RESULTS,
        description=(
            "Results per physical beam, straight off the StructuralModel: one envelope value "
            "per beam, the samples along each beam as a tree (t on the beam axis, not on the "
            "member), the full record as JSON - and a staleness check against the connected "
            "model. Wire the TimberModel into 'model' to get the Beam objects in the same order."
        ),
        inputs=[
            p("structural", desc="StructuralModel with results (from TektonRun).", optional=False),
            p("model", desc="TimberModel (optional). If given, 'beams' carries the Beam objects."),
            p("load_case", "int", desc="Load case. Empty = first available."),
            p("quantity", "str", desc="'N' | 'Vy' | 'Vz' | 'Mt' | 'My' | 'Mz' | 'displacement'. Forces signed (kN, kNm), displacement as magnitude (m)."),
        ],
        outputs=[
            o("beam_ids", "Element GUIDs, the order of every other output"),
            o("beams", "Beam objects in that order (only with 'model'; None where a GUID is missing)"),
            o("envelope", "Envelope value per beam"),
            o("samples", "Tree: per beam the quantity at each station along the beam"),
            o("params", "Tree: per beam the parameter t (0..1 on the beam axis) of each station"),
            o("analysis", "Full record per beam as JSON (samples + envelope)"),
            o("stale", "True when the results do not match the connected model"),
            o("info", "Quantity, load case, coverage, freshness"),
        ],
    ),
    dict(
        folder="tekton_attach_results",
        uid=15,
        name="Tekton Attach Results",
        nickname="TAttach",
        sub=SUB_RESULTS,
        description=(
            "Writes the results back onto the timber model "
            "(beam.attributes['analysis']) - with their provenance: which model state, "
            "which load case, when. A number without that is a liability question."
        ),
        inputs=[
            p("model", desc="TimberModel.", optional=False),
            p("structural", desc="StructuralModel with results.", optional=False),
            p("load_case", "int", desc="Load case. Empty: every load case with results."),
        ],
        outputs=[o("model", "TimberModel with analysis attributes"), o("attached", "Number of elements written to")],
    ),
    dict(
        folder="tekton_visualize",
        uid=16,
        name="Tekton Visualize",
        nickname="TViz",
        sub=SUB_RESULTS,
        description=(
            "Deformed shape and colour by result value: system lines through the deformed "
            "stations, the sections swept along them as meshes with a colour per station, "
            "and one colour per member. Values above the upper bound turn hard red - an "
            "exceedance should stand out, not fade away."
        ),
        inputs=[
            p("structural", desc="StructuralModel with results.", optional=False),
            p("load_case", "int", desc="Load case. Default: the first one with results."),
            p("quantity", "str", desc="'displacement' | 'N' | 'Vy' | 'Vz' | 'Mt' | 'My' | 'Mz' | 'utilization'. Forces by absolute value."),
            p("exaggeration", "float", desc="Factor on the deformation. Default 1 (true scale); 100 makes a stiff frame visible."),
            p("low", "float", desc="Lower bound of the scale. Default 0."),
            p("high", "float", desc="Upper bound. Default: the model's maximum (utilization: 1.0). Fix it to compare runs."),
            p("mesh", "bool", desc="Build the section meshes. Default True; False for lines only on large models."),
        ],
        outputs=[
            o("geometry", "Undeformed system lines"),
            o("colours", "Colour per member (its maximum)"),
            o("legend", "Labels of the scale"),
            o("deformed", "Deformed system lines, one polyline per member"),
            o("meshes", "Sections swept along the deformed lines, vertex-coloured by quantity"),
            o("values", "Maximum of the quantity per member, same order as the members"),
        ],
    ),
    dict(
        folder="tekton_inspect",
        uid=17,
        name="Tekton Inspect",
        nickname="TInspect",
        sub=SUB_RESULTS,
        description=(
            "Shows the analysis model itself: system lines, nodes, support symbols, "
            "release markers. For checking the idealisation before calculating - kept "
            "separate from the display of results."
        ),
        inputs=[
            p("structural", desc="StructuralModel.", optional=False),
            p("show", "str", access="list", desc="'members' | 'nodes' | 'supports' | 'releases' | 'surfaces'."),
            p("scale", "float", desc="Symbol size in document units."),
        ],
        outputs=[
            o("members", "System lines"),
            o("nodes", "Nodes"),
            o("supports", "Support symbols"),
            o("releases", "Release markers"),
        ],
    ),
    # ---------------- IO ----------------
    dict(
        folder="tekton_display",
        uid=25,
        name="Tekton Display",
        nickname="TDisplay",
        sub=SUB_RESULTS,
        description=(
            "The analysis model as a picture: elements as their sections, connections "
            "highlighted (rigid links dark, couplings magenta with white hinge spheres), "
            "supports as engineering symbols by condition (pyramid on a plate = pinned, "
            "rollers = free direction, ball, block = fixed) with a label, loads as arrows "
            "scaled by value, moments as rings, reactions in blue once results exist. "
            "Vertex-coloured meshes - no Custom Preview needed. The presentation view; "
            "Tekton Inspect is the bare debug view."
        ),
        inputs=[
            p("structural", desc="StructuralModel.", optional=False),
            p("show", "str", access="list", desc="Any of 'elements' | 'members' | 'connections' | 'supports' | 'loads' | 'reactions'. Empty = all."),
            p("load_case", "int", desc="Only this load case's loads and reactions. Empty = all loads, first result set."),
            p("scale", "float", desc="Symbol size in metres. Default 0.15."),
            p("load_scale", "float", desc="Arrow length per kN in metres. Default 0.25."),
            p("opacity", "float", desc="Opacity of the beams, 0..1. Default 0.35 - the connections inside stay visible."),
        ],
        outputs=[
            o("elements", "Section meshes of the beam members (drawn by the component with 'opacity'; solid meshes for downstream use)"),
            o("members", "System lines"),
            o("connections", "Connector rods, hinge spheres, shared-node markers"),
            o("supports", "Support symbols"),
            o("loads", "Load arrows and moment rings"),
            o("reactions", "Reaction arrows (with results)"),
            o("labels", "Text dots: support conditions, load and reaction values"),
            o("legend", "Counts and scales"),
        ],
    ),
    dict(
        folder="tekton_save_model",
        uid=18,
        name="Tekton Save Model",
        nickname="TSave",
        sub=SUB_IO,
        description=(
            "Writes the neutral model as JSON. That is also the handover format for "
            "engineers: traceable, versionable, open to discussion - including the "
            "assumptions report."
        ),
        inputs=[
            p("structural", desc="StructuralModel.", optional=False),
            p("filepath", "str", desc="Target path (.json).", optional=False),
            p("report", "str", access="list", desc="Assumptions report from TektonTranslate."),
            p("save", "bool", desc="Button.", optional=False),
        ],
        outputs=[o("path", "File that was written")],
    ),
    dict(
        folder="tekton_load_model",
        uid=19,
        name="Tekton Load Model",
        nickname="TLoad",
        sub=SUB_IO,
        description=(
            "Reads a neutral model (results included) from JSON back onto the canvas - "
            "for instance what the engineer sends back, or an earlier calculation run."
        ),
        inputs=[
            p("filepath", "str", desc="Source file (.json).", optional=False),
            p("repo", "str", desc="Path to the monorepo."),
        ],
        outputs=[
            o("structural", "StructuralModel"),
            o("info", "Short overview: nodes, members, load cases, results"),
        ],
    ),
    dict(
        folder="tekton_to_timber",
        uid=23,
        name="Tekton To Timber",
        nickname="TToTimber",
        sub=SUB_IO,
        description=(
            "Rebuilds the TimberModel from a StructuralModel: beams from their segments, "
            "sections and orientation, with the original GUIDs, results attached as "
            "beam.attributes['analysis']. Joints are not rebuilt (their types are not in the "
            "neutral model). Use it when only the analysis model is at hand - a JSON from the "
            "engineer, an earlier run - or to get the calculated model as timber elements."
        ),
        inputs=[
            p("structural", desc="StructuralModel, with or without results.", optional=False),
            p("attach", "bool", desc="Attach results to the beams. Default True."),
            p("repo", "str", desc="Path to the monorepo."),
        ],
        outputs=[
            o("model", "TimberModel"),
            o("report", "What was rebuilt, what was skipped"),
            o("connections", "Beam pairs that were connected, by GUID prefix"),
        ],
    ),
]


def make_placeholder_icon(path, seed):
    """Write a 24x24 PNG as a placeholder (no PIL, plain zlib/struct).

    The componentizer requires an icon.png; real icons come later. The colour
    varies per group so the components stay distinguishable in the menu as long
    as nothing drawn exists.
    """
    size = 24
    palette = {
        SUB_SETUP: (110, 110, 120),
        SUB_AUTHOR: (70, 130, 180),
        SUB_TRANSLATE: (60, 150, 110),
        SUB_RUN: (200, 130, 50),
        SUB_RESULTS: (170, 80, 140),
        SUB_IO: (120, 120, 70),
    }
    r, g, b = palette.get(seed, (100, 100, 100))

    rows = []
    for y in range(size):
        row = b"\x00"  # filter type
        for x in range(size):
            border = x < 2 or y < 2 or x >= size - 2 or y >= size - 2
            if border:
                row += bytes((r // 2, g // 2, b // 2, 255))
            else:
                row += bytes((r, g, b, 255))
        rows.append(row)
    raw = b"".join(rows)

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as handle:
        handle.write(png)


def main():
    if not os.path.isdir(COMPONENTS_DIR):
        os.makedirs(COMPONENTS_DIR)

    for spec in COMPONENTS:
        folder = os.path.join(COMPONENTS_DIR, spec["folder"])
        if not os.path.isdir(folder):
            os.makedirs(folder)

        metadata = {
            "name": spec["name"],
            "nickname": spec["nickname"],
            "category": CATEGORY,
            "subcategory": spec["sub"],
            "description": spec["description"],
            "exposure": 2,
            "instanceGuid": "7ec70000-0000-0000-0000-{:012d}".format(spec["uid"]),
            "ghpython": {
                "marshalGuids": True,
                "iconDisplay": 0,
                "inputParameters": spec["inputs"],
                "outputParameters": spec["outputs"],
            },
        }

        with open(os.path.join(folder, "metadata.json"), "w") as handle:
            json.dump(metadata, handle, indent=4)
            handle.write("\n")

        icon_path = os.path.join(folder, "icon.png")
        if not os.path.exists(icon_path):
            make_placeholder_icon(icon_path, spec["sub"])

        print("[x] {:<24} {}".format(spec["folder"], spec["sub"]))

    print("\n{} components written to {}".format(len(COMPONENTS), COMPONENTS_DIR))
    print("Create the missing code.py files, then: bash _componentizer/componetize.bash")


if __name__ == "__main__":
    main()
