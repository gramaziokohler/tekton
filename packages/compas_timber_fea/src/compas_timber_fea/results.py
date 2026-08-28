"""Attach analysis results back onto the timber design model.

FEA splits a physical beam into several members, and the Beam knows nothing
about that - it shouldn't. So results are attached at parameters along the
beam's own centerline: every member result sample maps through the identity
chain (member -> source_element_id -> Beam) and lands as (t, values) with
t in [0, 1] on the physical beam. The designer-facing number is the envelope
(per-beam maxima); the samples keep the full picture.

Everything here is offline: it consumes a StructuralModel whose ``results``
were filled by a backend reader.
"""

from datetime import datetime
from datetime import timezone

from compas_timber_fea.core.units import scale_to_meters

#: Key under which analysis data is stored in beam.attributes.
ANALYSIS_KEY = "analysis"


def attach_results_to_timber(structural_model, timber_model, result_sets=None):
    """Write per-beam samples and envelopes into ``beam.attributes["analysis"]``.

    Parameters
    ----------
    structural_model : StructuralModel
        The translated model, with ``results`` filled by a result reader.
    timber_model : TimberModel
        The source design model the results map back onto.
    result_sets : dict, optional
        {load_case_id: StructuralResultSet}; defaults to
        ``structural_model.results``.

    Returns
    -------
    dict
        {beam guid: analysis dict} for the beams that received results.
    """
    result_sets = result_sets if result_sets is not None else structural_model.results
    if not result_sets:
        return {}

    scale = scale_to_meters(structural_model.source_units)
    beams_by_guid = {str(beam.guid): beam for beam in timber_model.beams}
    points = {node.id: node.point for node in structural_model.nodes}
    members_by_beam = _members_by_source(structural_model)

    provenance = {
        "source": "tekton",
        "attached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_units": structural_model.source_units,
        "load_cases": sorted(result_sets.keys()),
    }

    attached = {}
    for guid, members in members_by_beam.items():
        beam = beams_by_guid.get(guid)
        if beam is None:
            continue

        start, length = _axis_in_meters(beam, scale)
        if not length:
            continue

        per_case = {}
        for load_case_id, result_set in result_sets.items():
            samples = _beam_samples(members, result_set, points, start, length)
            if samples:
                per_case[load_case_id] = {
                    "samples": samples,
                    "envelope": _envelope(samples),
                }

        if per_case:
            analysis = {"provenance": dict(provenance), "load_cases": per_case}
            beam.attributes[ANALYSIS_KEY] = analysis
            attached[guid] = analysis

    return attached


def _members_by_source(structural_model):
    grouped = {}
    for member in structural_model.members:
        if member.source_element_type == "beam" and member.source_element_id:
            grouped.setdefault(member.source_element_id, []).append(member)
    return grouped


def _axis_in_meters(beam, scale):
    line = beam.centerline
    start = (line.start.x * scale, line.start.y * scale, line.start.z * scale)
    end = (line.end.x * scale, line.end.y * scale, line.end.z * scale)
    direction = tuple(e - s for s, e in zip(start, end))
    length = sum(d * d for d in direction) ** 0.5
    return (start, length) if length > 1e-9 else (start, 0.0)


def _beam_samples(members, result_set, points, start, length):
    """Collect (t, values) samples for one beam from all its members."""
    samples = []
    for member in members:
        member_results = result_set.member_results.get(member.id)
        if not member_results:
            continue

        p_start = points.get(member.node_start)
        p_end = points.get(member.node_end)
        if p_start is None or p_end is None:
            continue

        direction = (p_end.x - p_start.x, p_end.y - p_start.y, p_end.z - p_start.z)
        member_length = sum(d * d for d in direction) ** 0.5

        for result in member_results:
            position = result.position
            if not result.metadata.get("position_normalized", True) and member_length:
                position = min(max(position / member_length, 0.0), 1.0)

            sample_point = _lerp(p_start, p_end, position)
            t = _param_from_start(sample_point, start, length)
            samples.append(
                (
                    round(t, 6),
                    {
                        "N": result.axial,
                        "Vy": result.shear_y,
                        "Vz": result.shear_z,
                        "Mt": result.torsion,
                        "My": result.moment_y,
                        "Mz": result.moment_z,
                    },
                )
            )
    samples.sort(key=lambda item: item[0])
    return samples


def _lerp(p_start, p_end, t):
    return (
        p_start.x + (p_end.x - p_start.x) * t,
        p_start.y + (p_end.y - p_start.y) * t,
        p_start.z + (p_end.z - p_start.z) * t,
    )


def _param_from_start(point, start, length):
    offset = tuple(point[i] - start[i] for i in range(3))
    distance = sum(o * o for o in offset) ** 0.5
    return min(max(distance / length, 0.0), 1.0)


def _envelope(samples):
    """Per-quantity maxima (by absolute value, sign kept) over all samples."""
    envelope = {}
    for _t, values in samples:
        for key, value in values.items():
            current = envelope.get(key)
            if current is None or abs(value) > abs(current):
                envelope[key] = value
    return envelope
