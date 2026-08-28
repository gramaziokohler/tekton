"""Tests for the COMPAS Timber -> neutral StructuralModel translation.

These run offline: no RFEM, no gRPC. They cover the translator's promises about
node reuse, member provenance, support derivation and zero-length filtering.
"""

import pytest
from compas.geometry import Line
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.translator import TimberToStructural


def _beam(start, end, width=0.1, height=0.2):
    return Beam.from_centerline(Line(start, end), width=width, height=height)


@pytest.fixture
def two_beam_model():
    """An L of two beams meeting at (2, 0, 0)."""
    model = TimberModel()
    model.add_element(_beam((0, 0, 0), (2, 0, 0)))
    model.add_element(_beam((2, 0, 0), (2, 2, 0)))
    return model


def test_translates_beams_to_members(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    assert len(structural_model.members) >= 2
    assert structural_model.nodes
    assert structural_model.sections


def test_members_carry_source_beam_provenance(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    beam_members = [m for m in structural_model.members if m.source_element_type == "beam"]
    assert beam_members, "no beam-derived members were produced"
    for member in beam_members:
        assert member.source_element_id, "member lost its source beam id"
        assert member.section_id is not None


def test_member_endpoints_reference_existing_nodes(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    node_ids = {node.id for node in structural_model.nodes}
    for member in structural_model.members:
        assert member.node_start in node_ids
        assert member.node_end in node_ids


def test_no_zero_length_members_survive(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    points = {node.id: node.point for node in structural_model.nodes}
    for member in structural_model.members:
        length = points[member.node_start].distance_to_point(points[member.node_end])
        assert length > 1e-6, f"member {member.id} has zero length"


def test_sections_are_deduplicated():
    """Beams sharing a cross-section must share one section entry."""
    model = TimberModel()
    model.add_element(_beam((0, 0, 0), (2, 0, 0), width=0.1, height=0.2))
    model.add_element(_beam((0, 1, 0), (2, 1, 0), width=0.1, height=0.2))

    structural_model = TimberToStructural().translate(model)

    beam_sections = {m.section_id for m in structural_model.members if m.source_element_type == "beam"}
    assert len(beam_sections) == 1


def test_supports_are_derived_from_marked_support_points():
    """Supports come only from explicitly marked points, never from geometry guessing."""
    model = TimberModel()
    beam = _beam((0, 0, 0), (4, 0, 0))
    beam.attributes["support_points"] = [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0)]
    model.add_element(beam)

    structural_model = TimberToStructural().translate(model)

    assert structural_model.supports, "marked support points produced no support"
    supported_nodes = {n for support in structural_model.supports for n in support.nodes}
    points = {node.id: node.point for node in structural_model.nodes}
    supported_points = sorted(round(points[n].x, 6) for n in supported_nodes)
    assert supported_points == [0.0, 4.0]


def test_model_without_support_points_has_no_supports(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    assert structural_model.supports == []


def test_self_weight_load_case_is_authored(two_beam_model):
    structural_model = TimberToStructural().translate(two_beam_model)

    assert len(structural_model.load_cases) == 1
    load_case = structural_model.load_cases[0]
    assert load_case.self_weight is True
    assert load_case.action_category == "PERMANENT"
