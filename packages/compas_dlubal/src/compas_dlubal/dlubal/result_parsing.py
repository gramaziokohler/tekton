"""Parse Dlubal result DataFrames into neutral result containers.

get_result_table returns DataFrames whose column names are produced by the
server, so they are resolved here against candidate lists rather than assumed.
Every parser is a pure function of a DataFrame - the live gRPC call stays in
the reader, and everything below it is testable offline.

Column-name candidates follow Dlubal's proto naming style (member_no,
location_x, axial_force_n, ...) as seen in the RSection result protos of the
pinned wheel; the first live run against RFEM should confirm them, and the raw
column list is kept in the result metadata for exactly that calibration.
"""

import math

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralNodeResult

from compas_dlubal.dlubal.conventions import vector_from_dlubal

#: Candidate column names per quantity, tried in order, case-insensitive.
MEMBER_FORCE_COLUMNS = {
    "member": ("member_no", "member", "no"),
    "location": ("location_x", "location", "x"),
    "axial": ("axial_force_n", "internal_force_n", "force_n", "n"),
    "shear_y": ("shear_force_v_y", "internal_force_vy", "v_y", "vy"),
    "shear_z": ("shear_force_v_z", "internal_force_vz", "v_z", "vz"),
    "torsion": ("torsional_moment_m_x", "torsional_moment_m_t", "internal_force_mt", "m_x", "mt"),
    "moment_y": ("bending_moment_m_y", "internal_force_my", "m_y", "my"),
    "moment_z": ("bending_moment_m_z", "internal_force_mz", "m_z", "mz"),
}

NODE_DEFORMATION_COLUMNS = {
    "node": ("node_no", "node", "no"),
    "ux": ("displacement_u_x", "u_x", "ux"),
    "uy": ("displacement_u_y", "u_y", "uy"),
    "uz": ("displacement_u_z", "u_z", "uz"),
    "rx": ("rotation_phi_x", "phi_x", "rx"),
    "ry": ("rotation_phi_y", "phi_y", "ry"),
    "rz": ("rotation_phi_z", "phi_z", "rz"),
}

SUPPORT_FORCE_COLUMNS = {
    "node": ("node_no", "node", "no"),
    "px": ("support_force_p_x", "force_p_x", "p_x", "px"),
    "py": ("support_force_p_y", "force_p_y", "p_y", "py"),
    "pz": ("support_force_p_z", "force_p_z", "p_z", "pz"),
    "mx": ("support_moment_m_x", "moment_m_x", "m_x", "mx"),
    "my": ("support_moment_m_y", "moment_m_y", "m_y", "my"),
    "mz": ("support_moment_m_z", "moment_m_z", "m_z", "mz"),
}


class ResultColumnError(KeyError):
    """A required result column could not be found in the DataFrame."""


def _resolve(dataframe, candidates, label, required=True):
    by_lower = {str(c).lower(): c for c in dataframe.columns}
    for candidate in candidates:
        if candidate in by_lower:
            return by_lower[candidate]
    if required:
        raise ResultColumnError(
            f"No column for {label!r} among candidates {candidates}. Available columns: {list(dataframe.columns)}"
        )
    return None


def _float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_member_internal_forces(dataframe, load_case_id, member_lengths=None):
    """DataFrame of the members-internal-forces table -> {member_id: [StructuralMemberResult]}.

    Positions come from the table in metres along the member; when
    ``member_lengths`` (member id -> length in m) is given, they are normalised
    to the 0..1 parameter the neutral containers use. Internal forces are in
    member-local axes and are passed through unchanged.
    """
    columns = {key: _resolve(dataframe, names, key, required=key in ("member", "location")) for key, names in MEMBER_FORCE_COLUMNS.items()}
    member_lengths = member_lengths or {}

    results = {}
    for _, row in dataframe.iterrows():
        member_id = _int(row[columns["member"]])
        if member_id is None:
            continue  # summary/header rows

        position = _float(row[columns["location"]])
        length = member_lengths.get(member_id)
        if length:
            position = min(max(position / length, 0.0), 1.0)

        def value(key, row=row):
            column = columns.get(key)
            return _float(row[column]) if column else 0.0

        results.setdefault(member_id, []).append(
            StructuralMemberResult(
                member_id=member_id,
                load_case_id=load_case_id,
                position=position,
                axial=value("axial"),
                shear_y=value("shear_y"),
                shear_z=value("shear_z"),
                torsion=value("torsion"),
                moment_y=value("moment_y"),
                moment_z=value("moment_z"),
                metadata={"position_normalized": bool(length)},
            )
        )
    return results


def parse_node_deformations(dataframe, load_case_id):
    """DataFrame of the nodes-global-deformations table -> {node_id: StructuralNodeResult}.

    Global vectors are converted from Dlubal's Z-down space back to the
    neutral Z-up convention at this boundary.
    """
    columns = {key: _resolve(dataframe, names, key, required=key == "node") for key, names in NODE_DEFORMATION_COLUMNS.items()}

    results = {}
    for _, row in dataframe.iterrows():
        node_id = _int(row[columns["node"]])
        if node_id is None:
            continue

        def value(key, row=row):
            column = columns.get(key)
            return _float(row[column]) if column else 0.0

        results[node_id] = StructuralNodeResult(
            node_id=node_id,
            load_case_id=load_case_id,
            displacement=vector_from_dlubal(value("ux"), value("uy"), value("uz")),
            rotation=vector_from_dlubal(value("rx"), value("ry"), value("rz")),
        )
    return results


def parse_support_forces(dataframe, load_case_id, node_results=None):
    """DataFrame of the nodes-support-forces table, merged into node results.

    Returns {node_id: StructuralNodeResult}; existing entries from
    ``node_results`` are enriched with reactions rather than replaced.
    """
    columns = {key: _resolve(dataframe, names, key, required=key == "node") for key, names in SUPPORT_FORCE_COLUMNS.items()}
    results = dict(node_results or {})

    for _, row in dataframe.iterrows():
        node_id = _int(row[columns["node"]])
        if node_id is None:
            continue

        def value(key, row=row):
            column = columns.get(key)
            return _float(row[column]) if column else 0.0

        entry = results.get(node_id) or StructuralNodeResult(node_id=node_id, load_case_id=load_case_id)
        entry.reaction_force = vector_from_dlubal(value("px"), value("py"), value("pz"))
        entry.reaction_moment = vector_from_dlubal(value("mx"), value("my"), value("mz"))
        results[node_id] = entry
    return results


def member_lengths_from_model(structural_model):
    """{member id: length in metres}, for normalising result positions."""
    points = {node.id: node.point for node in structural_model.nodes}
    lengths = {}
    for member in structural_model.members:
        start = points.get(member.node_start)
        end = points.get(member.node_end)
        if start is not None and end is not None:
            lengths[member.id] = start.distance_to_point(end)
    return lengths


__all__ = [
    "ResultColumnError",
    "parse_member_internal_forces",
    "parse_node_deformations",
    "parse_support_forces",
    "member_lengths_from_model",
]
