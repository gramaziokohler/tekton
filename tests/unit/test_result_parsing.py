"""Result DataFrame parsing, offline.

The DataFrames mimic Dlubal's column naming (as seen in the wheel's result
protos). The parsers must be tolerant about naming variants and summary rows,
and must convert global vectors back from Z-down to the neutral Z-up space.
"""

import pandas as pd
import pytest
from compas.geometry import Point

from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode

from compas_dlubal.dlubal.result_parsing import ResultColumnError
from compas_dlubal.dlubal.result_parsing import member_lengths_from_model
from compas_dlubal.dlubal.result_parsing import parse_member_deformations
from compas_dlubal.dlubal.result_parsing import parse_member_internal_forces
from compas_dlubal.dlubal.result_parsing import parse_node_deformations
from compas_dlubal.dlubal.result_parsing import parse_support_forces


def member_forces_frame():
    """As RFEM reports it: N and Nm."""
    return pd.DataFrame(
        {
            "member_no": [1, 1, 2],
            "location_x": [0.0, 2.0, 0.0],
            "axial_force_n": [-5000.0, -5000.0, 3000.0],
            "shear_force_v_z": [1000.0, -1000.0, 0.0],
            "bending_moment_m_y": [0.0, 2500.0, 0.0],
        }
    )


def test_member_forces_grouped_by_member():
    results = parse_member_internal_forces(member_forces_frame(), load_case_id=1)

    assert set(results) == {1, 2}
    assert len(results[1]) == 2
    first = results[1][0]
    assert first.load_case_id == 1
    assert first.axial == -5.0  # N -> kN
    assert first.moment_y == 0.0
    assert results[1][1].moment_y == 2.5  # Nm -> kNm


def test_positions_are_normalised_when_lengths_are_known():
    results = parse_member_internal_forces(member_forces_frame(), load_case_id=1, member_lengths={1: 4.0})

    positions = [r.position for r in results[1]]
    assert positions == [0.0, 0.5]
    assert all(r.metadata["position_normalized"] for r in results[1])
    # Member 2 has no known length: raw position, flagged as such.
    assert results[2][0].metadata["position_normalized"] is False


def test_missing_optional_force_columns_default_to_zero():
    frame = member_forces_frame().drop(columns=["shear_force_v_z"])

    results = parse_member_internal_forces(frame, load_case_id=1)

    assert results[1][0].shear_z == 0.0


def test_missing_member_column_is_a_clear_error():
    frame = member_forces_frame().drop(columns=["member_no"])
    # 'no' would also be accepted; remove any fallback candidates too.
    with pytest.raises(ResultColumnError, match="Available columns"):
        parse_member_internal_forces(frame, load_case_id=1)


def test_summary_rows_are_skipped():
    frame = member_forces_frame()
    frame.loc[len(frame)] = ["Total", None, None, None, None]

    results = parse_member_internal_forces(frame, load_case_id=1)

    assert set(results) == {1, 2}


def test_member_deformations_merge_into_force_rows():
    """RFEM samples deformations on the force station grid; matching rows must be enriched, not duplicated."""
    forces = parse_member_internal_forces(member_forces_frame(), load_case_id=1, member_lengths={1: 2.0})
    frame = pd.DataFrame({"member_no": [1, 1, 1], "location_x": [0.0, 1.0, 2.0], "u_x": [0.0, 0.001, 0.0], "u_z": [0.0, 0.004, 0.0]})

    results = parse_member_deformations(frame, load_case_id=1, member_lengths={1: 2.0}, member_results=forces)

    rows = results[1]
    assert [r.position for r in rows] == [0.0, 0.5, 1.0]
    assert rows[0].axial == -5.0  # force row kept
    assert rows[1].displacement.z == -0.004  # Z-down -> Z-up
    assert rows[1].axial == 0.0  # station without a force row


def test_member_deformations_stand_alone_without_forces():
    frame = pd.DataFrame({"member_no": [3], "location_x": [0.0], "u_y": [0.002]})

    results = parse_member_deformations(frame, load_case_id=1)

    assert results[3][0].displacement.y == -0.002


def test_node_deformations_convert_z_back_to_neutral():
    """RFEM is Z-down: a downward deflection (positive u_z there) is negative here."""
    frame = pd.DataFrame({"node_no": [7], "displacement_u_x": [0.001], "displacement_u_z": [0.004]})

    results = parse_node_deformations(frame, load_case_id=1)

    displacement = results[7].displacement
    assert displacement.x == 0.001
    assert displacement.z == -0.004


def test_support_forces_enrich_existing_node_results():
    deformations = parse_node_deformations(pd.DataFrame({"node_no": [3], "displacement_u_z": [0.002]}), load_case_id=1)
    reactions = pd.DataFrame({"node_no": [3], "support_force_p_z": [12500.0]})  # N

    results = parse_support_forces(reactions, load_case_id=1, node_results=deformations)

    entry = results[3]
    assert entry.displacement.z == -0.002, "deformation was lost while merging reactions"
    assert entry.reaction_force.z == -12.5  # kN, Z-up


def test_member_lengths_from_model():
    model = StructuralModel()
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(3, 0, 0)))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=2, section_id=1))

    assert member_lengths_from_model(model) == {1: 3.0}


def test_surface_results_merge_deformation_and_forces_per_mesh_node():
    """Two tables, one sample per (surface, mesh node): position Z-up, N/m -> kN/m, Nm/m -> kNm/m."""
    from compas_dlubal.dlubal.result_parsing import parse_surface_results

    deformations = pd.DataFrame({"surface_no": [1, 1], "mesh_node_no": [1, 2], "location_x": [0.0, 1.0], "location_y": [0.0, 0.0], "location_z": [-2.8, -2.8], "u_z": [0.001, 0.002]})
    forces = pd.DataFrame({"surface_no": [1, 1], "mesh_node_no": [1, 2], "location_x": [0.0, 1.0], "location_y": [0.0, 0.0], "location_z": [-2.8, -2.8], "m_x": [-15.5, 20.0], "n_x": [-22500.0, 100.0], "v_x": [5.0, 6.0]})

    results = parse_surface_results(deformations, forces, load_case_id=1)

    samples = results[1]
    assert len(samples) == 2
    assert samples[0].position.z == 2.8  # Dlubal Z-down -> neutral Z-up
    assert samples[0].displacement.z == -0.001
    assert samples[0].moment_x == -0.0155  # Nm/m -> kNm/m
    assert samples[0].membrane_force_x == -22.5  # N/m -> kN/m
    assert samples[0].metadata["v_x"] == 0.005


def test_surface_results_tolerate_a_missing_table():
    from compas_dlubal.dlubal.result_parsing import parse_surface_results

    forces = pd.DataFrame({"surface_no": [2], "mesh_node_no": [7], "m_y": [1000.0]})

    results = parse_surface_results(None, forces, load_case_id=1)

    assert results[2][0].moment_y == 1.0
    assert results[2][0].position is None
