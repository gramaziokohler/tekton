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
from compas_dlubal.dlubal.result_parsing import parse_member_internal_forces
from compas_dlubal.dlubal.result_parsing import parse_node_deformations
from compas_dlubal.dlubal.result_parsing import parse_support_forces


def member_forces_frame():
    return pd.DataFrame(
        {
            "member_no": [1, 1, 2],
            "location_x": [0.0, 2.0, 0.0],
            "axial_force_n": [-5.0, -5.0, 3.0],
            "shear_force_v_z": [1.0, -1.0, 0.0],
            "bending_moment_m_y": [0.0, 2.5, 0.0],
        }
    )


def test_member_forces_grouped_by_member():
    results = parse_member_internal_forces(member_forces_frame(), load_case_id=1)

    assert set(results) == {1, 2}
    assert len(results[1]) == 2
    first = results[1][0]
    assert first.load_case_id == 1
    assert first.axial == -5.0
    assert first.moment_y == 0.0
    assert results[1][1].moment_y == 2.5


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


def test_node_deformations_convert_z_back_to_neutral():
    """RFEM is Z-down: a downward deflection (positive u_z there) is negative here."""
    frame = pd.DataFrame({"node_no": [7], "displacement_u_x": [0.001], "displacement_u_z": [0.004]})

    results = parse_node_deformations(frame, load_case_id=1)

    displacement = results[7].displacement
    assert displacement.x == 0.001
    assert displacement.z == -0.004


def test_support_forces_enrich_existing_node_results():
    deformations = parse_node_deformations(pd.DataFrame({"node_no": [3], "displacement_u_z": [0.002]}), load_case_id=1)
    reactions = pd.DataFrame({"node_no": [3], "support_force_p_z": [12.5]})

    results = parse_support_forces(reactions, load_case_id=1, node_results=deformations)

    entry = results[3]
    assert entry.displacement.z == -0.002, "deformation was lost while merging reactions"
    assert entry.reaction_force.z == -12.5


def test_member_lengths_from_model():
    model = StructuralModel()
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(3, 0, 0)))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=2, section_id=1))

    assert member_lengths_from_model(model) == {1: 3.0}
