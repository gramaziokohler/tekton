"""Tekton Results - results per physical beam, as numbers and trees.

The analysed member is not the physical beam: a beam is split into several
members at joints and supports. This component brings them back together -
the mapping goes RFEM member number -> neutral member id -> source_element_id
-> beam, and every sample lands at the parameter t on the *beam* axis, so a
beam split in three does not show 0..1 three times over.

Two things it does that nothing else does: it checks the results against the
connected model (`stale` - Grasshopper holds on to old outputs, and a number
from an older model state looks just as right as a fresh one), and it works
straight off the StructuralModel, no timber model needed. Wire the
TimberModel into `model` anyway and the Beam objects come out in the same
order, ready for geometry and colouring.

Utilisation is the one quantity still missing: it comes from RFEM's design
add-on and is not wired up.
"""
# venv: tekton-test
# r: compas, compas_timber

import json
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

QUANTITIES = ("N", "Vy", "Vz", "Mt", "My", "Mz", "displacement", "utilization")


def _magnitude(value):
    if isinstance(value, (list, tuple)):
        return sum(c * c for c in value) ** 0.5
    return value


# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
model = model  # type: ignore # noqa: F821
load_case: int  # type: ignore
quantity: str  # type: ignore

# --------------------- SCRIPT ---------------------

# Drop-down on 'quantity' the moment the component lands on the canvas. Needs
# the repo path for the import; without it the menu simply does not appear
# and TektonInfo says what is missing.
try:
    _setup()
    from tekton_gh.rhino_io import attach_value_list

    attach_value_list(ghenv, ['displacement', 'N', 'Vy', 'Vz', 'Mt', 'My', 'Mz'], param_index=3, nickname="Quantity")  # type: ignore # noqa: F821
except Exception:
    pass

import Grasshopper  # noqa: E402
from Grasshopper.Kernel.Data import GH_Path  # noqa: E402

beam_ids = []
beams = []
envelope = []
samples = Grasshopper.DataTree[object]()
params = Grasshopper.DataTree[object]()
analysis = []
stale = False
info = []

if structural is None:
    _warn("No StructuralModel connected.")
else:
    _setup()
    import importlib
    import compas_timber_fea.results
    importlib.reload(compas_timber_fea.results)
    from compas_timber_fea.results import samples_by_beam

    quantity = quantity or "displacement"
    if quantity == "utilization":
        _warn("Utilisation comes from RFEM's design add-on and is not wired up yet. Deflection is shown instead.")
        quantity = "displacement"
    elif quantity not in QUANTITIES:
        _warn("Unknown quantity '{}'. Allowed: {}.".format(quantity, ", ".join(QUANTITIES)))
        quantity = "displacement"

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("The model carries no results. Run TektonRun first.")
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)
        if result_set is None:
            _warn("Load case {} not in the results. Available: {}.".format(case_id, sorted(results)))
        else:
            by_guid = {str(b.guid): b for b in model.beams} if model is not None else {}
            missing = 0
            for index, (guid, record) in enumerate(samples_by_beam(structural, result_set).items()):
                beam_ids.append(guid)
                beam = by_guid.get(guid)
                beams.append(beam)
                if model is not None and beam is None:
                    missing += 1
                envelope.append(_magnitude(record["envelope"].get(quantity)))
                analysis.append(json.dumps(record, default=str))
                path = GH_Path(index)
                for t, values in record["samples"]:
                    if quantity in values:
                        params.Add(t, path)
                        samples.Add(_magnitude(values[quantity]), path)

            info = [
                "Quantity: {} ({})".format(quantity, "m, magnitude" if quantity == "displacement" else "kN / kNm, signed"),
                "Load case: {} of {}".format(case_id, sorted(results)),
                "Beams with results: {}".format(len(beam_ids)),
            ]
            if model is not None:
                info.append("Beam objects matched: {} of {}".format(len(beam_ids) - missing, len(beam_ids)))
                if missing:
                    _warn("{} beams with results are not in the connected TimberModel - GUIDs no longer line up.".format(missing))

            # Freshness. Results that silently describe an older model state
            # are the most dangerous failure mode of this workflow.
            from tekton_gh.worker import model_fingerprint

            metadata = getattr(result_set, "metadata", {}) or {}
            stamped = metadata.get("model_fingerprint")
            if not stamped:
                _warn("Results without a provenance stamp - freshness cannot be checked.")
            else:
                current = model_fingerprint(structural)
                stale = current != stamped
                if stale:
                    _warn("STALE: the results belong to model state {}, but {} is connected. Recalculate.".format(stamped, current))
                else:
                    info.append("Fresh: results match the connected model ({}).".format(current))
            if metadata.get("calculated_at"):
                info.append("Calculated: {}".format(metadata["calculated_at"]))

for line in info:
    print(line)
