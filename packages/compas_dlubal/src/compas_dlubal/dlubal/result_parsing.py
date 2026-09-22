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

from compas.geometry import Point

from compas_timber_fea.core.model import StructuralMemberResult
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralSurfaceResult

from compas_dlubal.dlubal.conventions import force_from_dlubal
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

MEMBER_DEFORMATION_COLUMNS = {
    "member": ("member_no", "member", "no"),
    "location": ("location_x", "location", "x"),
    "ux": ("displacement_u_x", "u_x", "ux"),
    "uy": ("displacement_u_y", "u_y", "uy"),
    "uz": ("displacement_u_z", "u_z", "uz"),
}

#: Surface tables come per mesh node, with the node's position; both the
#: deformation and the internal-force table share (surface_no, mesh_node_no).
SURFACE_COLUMNS = {
    "surface": ("surface_no", "surface", "no"),
    "mesh_node": ("mesh_node_no", "mesh_node", "node_no"),
    "x": ("location_x", "x"),
    "y": ("location_y", "y"),
    "z": ("location_z", "z"),
    "ux": ("displacement_u_x", "u_x", "ux"),
    "uy": ("displacement_u_y", "u_y", "uy"),
    "uz": ("displacement_u_z", "u_z", "uz"),
    "n_x": ("n_x", "nx"),
    "n_y": ("n_y", "ny"),
    "n_xy": ("n_xy", "nxy"),
    "m_x": ("m_x", "mx"),
    "m_y": ("m_y", "my"),
    "m_xy": ("m_xy", "mxy"),
    "v_x": ("v_x", "vx"),
    "v_y": ("v_y", "vy"),
}

#: The timber design add-on's ratio table (TIMBER_DESIGN_MEMBERS_DESIGN_RATIOS_BY_LOCATION),
#: as delivered by RFEM 6.13 on 2026-09-18. One row per member, location and
#: check; the loading label is the *design* loading (a combination, "CO1" or
#: "LK1" depending on the UI language), never a bare load case.
DESIGN_RATIO_COLUMNS = {
    "member": ("member_no", "member", "no"),
    "location": ("location_x", "location", "x"),
    "ratio": ("design_ratio", "ratio", "eta"),
    "check_type": ("design_check_type", "check_type"),
    "description": ("design_check_description", "description"),
    "loading": ("loading",),
    "design_situation": ("design_situation_no", "design_situation"),
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

        # RFEM reports N and Nm; the neutral containers hold kN and kNm.
        results.setdefault(member_id, []).append(
            StructuralMemberResult(
                member_id=member_id,
                load_case_id=load_case_id,
                position=position,
                axial=force_from_dlubal(value("axial")),
                shear_y=force_from_dlubal(value("shear_y")),
                shear_z=force_from_dlubal(value("shear_z")),
                torsion=force_from_dlubal(value("torsion")),
                moment_y=force_from_dlubal(value("moment_y")),
                moment_z=force_from_dlubal(value("moment_z")),
                metadata={"position_normalized": bool(length)},
            )
        )
    return results


def parse_member_deformations(dataframe, load_case_id, member_lengths=None, member_results=None):
    """DataFrame of the members-global-deformations table, merged into member results.

    RFEM reports deformations on the same station grid as the internal
    forces, so each row is matched to the existing StructuralMemberResult at
    that position (within a small tolerance on the 0..1 parameter). Stations
    without a force row get a result of their own, so a deformed shape can be
    drawn even when forces were not read. Global vectors come back into the
    neutral Z-up convention.
    """
    columns = {key: _resolve(dataframe, names, key, required=key in ("member", "location")) for key, names in MEMBER_DEFORMATION_COLUMNS.items()}
    member_lengths = member_lengths or {}
    results = dict(member_results or {})

    for _, row in dataframe.iterrows():
        member_id = _int(row[columns["member"]])
        if member_id is None:
            continue

        position = _float(row[columns["location"]])
        length = member_lengths.get(member_id)
        if length:
            position = min(max(position / length, 0.0), 1.0)

        def value(key, row=row):
            column = columns.get(key)
            return _float(row[column]) if column else 0.0

        displacement = vector_from_dlubal(value("ux"), value("uy"), value("uz"))
        rows = results.setdefault(member_id, [])
        match = next((r for r in rows if abs(r.position - position) < 1e-4), None)
        if match is None:
            match = StructuralMemberResult(
                member_id=member_id,
                load_case_id=load_case_id,
                position=position,
                metadata={"position_normalized": bool(length)},
            )
            rows.append(match)
            rows.sort(key=lambda r: r.position)
        match.displacement = displacement
    return results


def parse_member_design_ratios(dataframe, load_case_id, member_lengths=None, member_results=None):
    """Timber-design ratio table -> ``metadata["utilization"]`` on the member results.

    RFEM reports the ratios on the same station grid as the internal forces,
    so each row is matched to the StructuralMemberResult at that position;
    stations the static reader did not produce get a result of their own. Per
    station the *largest* ratio over all checks and all design loadings is
    kept, together with the check that produced it::

        metadata["utilization"]       0.299          (max ratio at this station)
        metadata["governing_check"]   "Doppelbiegung und Drucknormalkraft nach 6.2.4"
        metadata["check_type"]        "SP6300.00"    (RFEM's check code)
        metadata["design_loading"]    "LK1"          (the combination it came from)

    The ratio belongs to a design combination, not to the load case whose
    result set it lands in; the reader records the mapping in the result-set
    metadata. Rows with an empty or non-numeric ratio are skipped.

    Returns
    -------
    dict
        The (updated) ``{member_id: [StructuralMemberResult]}`` mapping.
    """
    columns = {key: _resolve(dataframe, names, key, required=key in ("member", "location", "ratio")) for key, names in DESIGN_RATIO_COLUMNS.items()}
    member_lengths = member_lengths or {}
    results = dict(member_results or {})

    for _, row in dataframe.iterrows():
        member_id = _int(row[columns["member"]])
        if member_id is None:
            continue
        ratio = _float(row[columns["ratio"]], default=None)
        if ratio is None:
            continue

        position = _float(row[columns["location"]])
        length = member_lengths.get(member_id)
        if length:
            position = min(max(position / length, 0.0), 1.0)

        def text(key, row=row):
            column = columns.get(key)
            if column is None:
                return ""
            value = row[column]
            return "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)

        rows = results.setdefault(member_id, [])
        match = next((r for r in rows if abs(r.position - position) < 1e-4), None)
        if match is None:
            match = StructuralMemberResult(
                member_id=member_id,
                load_case_id=load_case_id,
                position=position,
                metadata={"position_normalized": bool(length)},
            )
            rows.append(match)
            rows.sort(key=lambda r: r.position)

        current = match.metadata.get("utilization")
        if current is None or ratio > current:
            match.metadata["utilization"] = ratio
            match.metadata["governing_check"] = text("description")
            match.metadata["check_type"] = text("check_type")
            match.metadata["design_loading"] = text("loading")
    return results


def split_design_ratios_by_loading(dataframe):
    """{combination number: sub-frame} from the ratio table's loading labels.

    The label is language-dependent ("CO1" / "LK1"); the number is not.
    Rows whose label carries no number are dropped.
    """
    column = _resolve(dataframe, DESIGN_RATIO_COLUMNS["loading"], "loading", required=False)
    if column is None:
        return {}
    numbers = dataframe[column].astype(str).str.extract(r"(\d+)")[0]
    out = {}
    for value in numbers.dropna().unique():
        out[int(value)] = dataframe[numbers == value]
    return out


def design_ratio_summary(dataframe):
    """What the ratio table covers: its design loadings and situations, for the result-set metadata."""
    out = {"loadings": [], "design_situations": []}
    loading = _resolve(dataframe, DESIGN_RATIO_COLUMNS["loading"], "loading", required=False)
    situation = _resolve(dataframe, DESIGN_RATIO_COLUMNS["design_situation"], "design_situation", required=False)
    if loading is not None:
        out["loadings"] = sorted({str(v) for v in dataframe[loading].dropna()})
    if situation is not None:
        out["design_situations"] = sorted({_int(v) for v in dataframe[situation].dropna() if _int(v) is not None})
    return out


def parse_surface_results(deformations, forces, load_case_id):
    """Surface deformation + basic internal force tables (per mesh node) -> {surface_id: [StructuralSurfaceResult]}.

    Either frame may be None. Rows are matched on (surface, mesh node); the
    position comes back into the neutral Z-up space, forces from N/m and Nm/m
    into kN/m and kNm/m. Membrane forces land in ``membrane_force_*``,
    moments in ``moment_*``, shear in ``metadata["v_x"|"v_y"]``.
    """
    samples = {}

    def rows_of(frame, keys):
        if frame is None or len(frame) == 0:
            return
        columns = {key: _resolve(frame, names, key, required=key in ("surface", "mesh_node")) for key, names in SURFACE_COLUMNS.items()}
        for _, row in frame.iterrows():
            surface_id = _int(row[columns["surface"]])
            node = _int(row[columns["mesh_node"]])
            if surface_id is None or node is None:
                continue

            def value(key, row=row):
                column = columns.get(key)
                return _float(row[column]) if column else 0.0

            sample = samples.get((surface_id, node))
            if sample is None:
                sample = StructuralSurfaceResult(surface_id=surface_id, load_case_id=load_case_id)
                if columns.get("x"):
                    x, y, z = vector_from_dlubal(value("x"), value("y"), value("z"))
                    sample.position = Point(x, y, z)
                samples[(surface_id, node)] = sample
            keys(sample, value)

    def deformation(sample, value):
        sample.displacement = vector_from_dlubal(value("ux"), value("uy"), value("uz"))

    def force(sample, value):
        sample.membrane_force_x = force_from_dlubal(value("n_x"))
        sample.membrane_force_y = force_from_dlubal(value("n_y"))
        sample.membrane_force_xy = force_from_dlubal(value("n_xy"))
        sample.moment_x = force_from_dlubal(value("m_x"))
        sample.moment_y = force_from_dlubal(value("m_y"))
        sample.moment_xy = force_from_dlubal(value("m_xy"))
        sample.metadata["v_x"] = force_from_dlubal(value("v_x"))
        sample.metadata["v_y"] = force_from_dlubal(value("v_y"))

    rows_of(deformations, deformation)
    rows_of(forces, force)

    results = {}
    for (surface_id, _node), sample in sorted(samples.items()):
        results.setdefault(surface_id, []).append(sample)
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
        # RFEM's support forces are the forces on the support; the neutral
        # model stores the reaction on the structure (what OpenSees reports,
        # and what the Display arrows point with). Hence the negation.
        entry.reaction_force = vector_from_dlubal(*(-force_from_dlubal(value(k)) for k in ("px", "py", "pz")))
        entry.reaction_moment = vector_from_dlubal(*(-force_from_dlubal(value(k)) for k in ("mx", "my", "mz")))
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
    "parse_member_deformations",
    "parse_node_deformations",
    "parse_surface_results",
    "parse_support_forces",
    "member_lengths_from_model",
]
