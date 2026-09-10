"""Tekton Attach Results - results back onto the timber model.

Writes `beam.attributes['analysis']` with envelope values, sample points and
provenance.

Provenance is mandatory, not decoration: a number without 'which model state,
which combination, when' is a liability question. The worst failure mode is
results silently surviving a design change.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Attach"  # type: ignore # noqa: F821


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
model = model  # type: ignore # noqa: F821
structural = structural  # type: ignore # noqa: F821
load_case: int  # type: ignore

# --------------------- SCRIPT ---------------------

attached = 0

if model is None or structural is None:
    _warn("model and structural are both needed.")
else:
    _setup()
    import time

    results = getattr(structural, "results", {}) or {}
    if not results:
        _warn("No results in the model - run TektonRun first.")
    else:
        case_id = int(load_case) if load_case else sorted(results)[0]
        result_set = results.get(case_id)

        if result_set is None:
            _warn("Load case {} does not exist.".format(case_id))
        else:
            member_source = {m.id: str(m.source_element_id) for m in structural.members}
            per_beam = {}
            for member_id, rows in (result_set.member_results or {}).items():
                source = member_source.get(member_id)
                if source is None:
                    continue
                per_beam.setdefault(source, []).extend(rows)

            provenance = {
                "load_case": case_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": (getattr(result_set, "metadata", {}) or {}).get("source", "unknown"),
            }

            for beam in model.beams:
                rows = per_beam.get(str(beam.guid))
                if not rows:
                    continue
                beam.attributes["analysis"] = {
                    "provenance": provenance,
                    "samples": [
                        (row.position, {
                            "N": row.axial, "Vy": row.shear_y, "Vz": row.shear_z,
                            "Mt": row.torsion, "My": row.moment_y, "Mz": row.moment_z,
                            "displacement": row.displacement,
                        })
                        for row in rows
                    ],
                    "envelope": {
                        "max_displacement": max((abs(r.displacement or 0.0) for r in rows), default=0.0),
                        "max_moment_y": max((abs(r.moment_y or 0.0) for r in rows), default=0.0),
                        # TODO(scaffold): max_utilization, once the design
                        # add-on is wired up.
                    },
                }
                attached += 1

            print("Results attached to {} of {} elements.".format(attached, len(list(model.beams))))
            if attached == 0:
                _warn(
                    "No element matched. Usually the element GUIDs no longer "
                    "line up - the timber model was changed after calculating."
                )
