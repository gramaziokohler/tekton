"""Tekton Results - results per physical beam.

Delivers envelope values (what the designer sees first) and sample points along
the axis (for diagrams). The mapping goes through the element GUID: RFEM member
number -> neutral member ID -> source_element_id -> beam. The analysed member is
not the physical beam - a beam is split into several members, whose results are
brought back together here.

Utilisation is the one quantity still missing: it comes from RFEM's design
add-on and is not wired up. Internal forces, deflections and support reactions
are read.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Results"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own.
    os.environ["TEKTON_REPO"] = root
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore
quantity: str  # type: ignore

# --------------------- SCRIPT ---------------------

beam_ids = []
envelope = []
samples = []
stale = False

QUANTITIES = {
    "utilization": None,  # comes from the design add-on, not yet tested
    "displacement": "displacement",
    "N": "axial",
    "My": "moment_y",
    "Mz": "moment_z",
    "Vy": "shear_y",
    "Vz": "shear_z",
}

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("The model carries no results. Run TektonRun first.")
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)
        if result_set is None:
            _warn("Load case {} not in the results. Available: {}.".format(case_id, sorted(results)))
        else:
            key = quantity or "utilization"
            attribute = QUANTITIES.get(key, "displacement")
            if key == "utilization":
                _warn(
                    "Utilisation comes from RFEM's design add-on and is not "
                    "wired up yet. Deflection is shown instead."
                )
                attribute = "displacement"
            elif key not in QUANTITIES:
                _warn("Unknown quantity '{}'. Allowed: {}.".format(key, ", ".join(sorted(QUANTITIES))))

            # Group member results by element GUID: several members belong to
            # the same physical beam.
            member_source = {m.id: m.source_element_id for m in structural.members}
            per_beam = {}
            for member_id, rows in (result_set.member_results or {}).items():
                source = member_source.get(member_id)
                if source is None:
                    continue
                per_beam.setdefault(str(source), []).extend(rows)

            for source, rows in sorted(per_beam.items()):
                values = [abs(getattr(row, attribute, 0.0) or 0.0) for row in rows]
                beam_ids.append(source)
                envelope.append(max(values) if values else 0.0)
                samples.append([(row.position, getattr(row, attribute, 0.0)) for row in rows])

            print("{} elements, load case {}, quantity '{}'".format(len(beam_ids), case_id, key))

            # Check freshness. Results that silently describe an older model
            # state are the most dangerous failure mode of this workflow:
            # Grasshopper holds on to old outputs, and after a change a number
            # looks just as right as it did before.
            from tekton_gh.worker import model_fingerprint

            metadata = getattr(result_set, "metadata", {}) or {}
            stamped = metadata.get("model_fingerprint")
            if not stamped:
                _warn("Results without a provenance stamp - freshness cannot be checked.")
            else:
                current = model_fingerprint(structural)
                stale = current != stamped
                if stale:
                    _warn(
                        "STALE: the results belong to model state {}, but {} "
                        "is connected. Recalculate.".format(stamped, current)
                    )
                else:
                    print("Model state {} - results current{}.".format(
                        stamped,
                        ", calculated {}".format(metadata["calculated_at"]) if metadata.get("calculated_at") else ""))
