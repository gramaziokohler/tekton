"""Superpose load case results into combination results.

A combination is not solved; it is assembled. For a linear-elastic model the
results of a factored sum of load cases are the factored sum of the results,
so running n cases and combining them beats running every combination
through the solver - and it is what RFEM does internally too.

The limit is worth stating plainly: this holds only while the model is
linear. Second-order effects, contact, or a material that yields all break
it, and none of them are in the neutral model today. When one arrives, the
combination has to go back through the solver, and this module has to refuse
rather than quietly produce numbers that look right.
"""

from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSurfaceResult

#: Result set ids for combinations start here, clear of the load case ids
#: they are built from.
COMBINATION_ID_BASE = 1000


class SuperpositionError(ValueError):
    """Raised when a combination cannot be assembled from what was solved."""


def _scaled_vector(vector, factor):
    if vector is None:
        return None
    return Vector(vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _add_vector(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return Vector(a[0] + b[0], a[1] + b[1], a[2] + b[2])


def combine_results(model, combination, result_id=None):
    """Assemble one :class:`StructuralResultSet` for a load combination.

    Parameters
    ----------
    model : StructuralModel
        With ``results`` for every load case the combination references.
    combination : LoadCombination
        Its ``factors`` map load case ids to factors.
    result_id : int, optional
        Id for the new result set; defaults to ``COMBINATION_ID_BASE + id``.

    Returns
    -------
    StructuralResultSet

    Raises
    ------
    SuperpositionError
        When a referenced load case has no results. Silently dropping it
        would understate the combination - the one direction an engineer
        must never be surprised in.
    """
    factors = dict(getattr(combination, "factors", {}) or {})
    if not factors:
        raise SuperpositionError(
            "Combination {!r} has no factors.".format(getattr(combination, "name", combination)))

    missing = [case_id for case_id in factors if case_id not in (model.results or {})]
    if missing:
        raise SuperpositionError(
            "Combination {!r} references load case(s) {} that were not solved. "
            "Run them first - a combination missing a case understates the result.".format(
                getattr(combination, "name", combination), sorted(missing)))

    nodes = {}
    members = {}
    surfaces = {}

    for case_id, factor in sorted(factors.items()):
        factor = float(factor)
        if factor == 0.0:
            continue
        source = model.results[case_id]

        for node_id, result in (source.node_results or {}).items():
            target = nodes.get(node_id)
            if target is None:
                target = StructuralNodeResult(node_id=node_id, load_case_id=0)
                nodes[node_id] = target
            target.displacement = _add_vector(target.displacement, _scaled_vector(result.displacement, factor))
            target.rotation = _add_vector(target.rotation, _scaled_vector(result.rotation, factor))
            if result.reaction_force is not None:
                target.reaction_force = _add_vector(
                    target.reaction_force, _scaled_vector(result.reaction_force, factor))
            if result.reaction_moment is not None:
                target.reaction_moment = _add_vector(
                    target.reaction_moment, _scaled_vector(result.reaction_moment, factor))

        for member_id, samples in (source.member_results or {}).items():
            rows = members.setdefault(member_id, [])
            for index, sample in enumerate(samples or []):
                if index < len(rows):
                    target = rows[index]
                    if abs(target.position - sample.position) > 1e-9:
                        raise SuperpositionError(
                            "Member {} is sampled at different positions across load cases; "
                            "they cannot be superposed station by station.".format(member_id))
                else:
                    target = StructuralMemberResult(
                        member_id=member_id, load_case_id=0, position=sample.position)
                    rows.append(target)
                target.axial += sample.axial * factor
                target.shear_y += sample.shear_y * factor
                target.shear_z += sample.shear_z * factor
                target.torsion += sample.torsion * factor
                target.moment_y += sample.moment_y * factor
                target.moment_z += sample.moment_z * factor
                if sample.displacement is not None:
                    target.displacement = _add_vector(
                        target.displacement, _scaled_vector(sample.displacement, factor))

        for surface_id, samples in (source.surface_results or {}).items():
            rows = surfaces.setdefault(surface_id, [])
            for index, sample in enumerate(samples or []):
                if index < len(rows):
                    target = rows[index]
                else:
                    target = StructuralSurfaceResult(
                        surface_id=surface_id, load_case_id=0,
                        position=Point(*sample.position) if sample.position is not None else None,
                        metadata=dict(sample.metadata or {}))
                    rows.append(target)
                target.membrane_force_x += sample.membrane_force_x * factor
                target.membrane_force_y += sample.membrane_force_y * factor
                target.membrane_force_xy += sample.membrane_force_xy * factor
                target.moment_x += sample.moment_x * factor
                target.moment_y += sample.moment_y * factor
                target.moment_xy += sample.moment_xy * factor
                if sample.displacement is not None:
                    target.displacement = _add_vector(
                        target.displacement, _scaled_vector(sample.displacement, factor))

    case_id = result_id if result_id is not None else COMBINATION_ID_BASE + int(getattr(combination, "id", 0))
    for result in nodes.values():
        result.load_case_id = case_id
    for rows in members.values():
        for result in rows:
            result.load_case_id = case_id
    for rows in surfaces.values():
        for result in rows:
            result.load_case_id = case_id

    return StructuralResultSet(
        load_case_id=case_id,
        name=getattr(combination, "name", "combination"),
        node_results=nodes,
        member_results=members,
        surface_results=surfaces,
        metadata={
            "source": "superposition",
            "combination_id": getattr(combination, "id", None),
            "combination_type": getattr(combination, "combination_type", ""),
            "factors": {str(k): float(v) for k, v in factors.items()},
            "linear_only": True,
        },
    )


def combine_all(model, combinations=None, into_model=True):
    """Assemble every combination of the model.

    Parameters
    ----------
    model : StructuralModel
    combinations : list, optional
        Defaults to ``model.load_combinations``.
    into_model : bool
        Write the assembled sets into ``model.results`` as well, so
        everything downstream - Summary, design checks, Visualize - sees
        combinations exactly the way it sees load cases.

    Returns
    -------
    dict
        ``{result id: StructuralResultSet}``
    """
    combinations = combinations if combinations is not None else list(getattr(model, "load_combinations", []) or [])
    out = {}
    for combination in combinations:
        result_set = combine_results(model, combination)
        out[result_set.load_case_id] = result_set
        if into_model:
            model.results[result_set.load_case_id] = result_set
    return out
