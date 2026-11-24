"""Translate uses the TimberModel's structural segments as it finds them.

A model can arrive with its segments already made upstream (a design canvas
that sets its own discretisation). compas_timber appends segments, so the
translator must not generate a second set on top - nor add one on every
re-solve. And a beam split into several members must not report its support
points as unmatched just because one of the pieces doesn't end on them.
"""

from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Vector
from compas_timber.connections import TButtJoint
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from compas_timber_fea.translator import TimberToStructural


def _girder_and_leg():
    """A 4 m girder on two supports, a 3 m leg T-butted to its middle, fixed at the foot."""
    model = TimberModel()
    girder = Beam.from_centerline(Line(Point(0, 0, 0), Point(4, 0, 0)), 0.2, 0.4, z_vector=Vector(0, 0, 1))
    leg = Beam.from_centerline(Line(Point(2, 0, -3), Point(2, 0, 0)), 0.2, 0.4, z_vector=Vector(1, 0, 0))
    model.add_element(girder)
    model.add_element(leg)
    TButtJoint.create(model, leg, girder)
    girder.attributes["support_points"] = [[0, 0, 0, "pinned"], [4, 0, 0, "pinned"]]
    leg.attributes["support_points"] = [[2, 0, -3, "fixed"]]
    return model, girder, leg


def _segment_counts(model):
    return [len(model.get_beam_structural_segments(beam)) for beam in model.beams]


def test_segments_made_once_when_missing():
    model, _, _ = _girder_and_leg()

    TimberToStructural().translate(model)

    assert _segment_counts(model) == [2, 1]  # the girder split at the leg, the leg whole


def test_existing_segments_kept_as_they_are():
    model, _, _ = _girder_and_leg()
    model.create_beam_structural_segments()
    before = [[seg.line for seg in model.get_beam_structural_segments(b)] for b in model.beams]

    TimberToStructural().translate(model)

    after = [[seg.line for seg in model.get_beam_structural_segments(b)] for b in model.beams]
    assert after == before


def test_repeated_translate_adds_nothing():
    model, _, _ = _girder_and_leg()

    for _ in range(3):  # a Grasshopper re-solve translates the same model again
        structural = TimberToStructural().translate(model)

    assert _segment_counts(model) == [2, 1]
    assert len(structural.members) == 3


def test_support_on_split_beam_not_reported_unmatched():
    model, _, _ = _girder_and_leg()

    translator = TimberToStructural()
    structural = translator.translate(model)

    assert not [line for line in translator.report if "matched no structural node" in line]
    supported = {node for support in structural.supports for node in support.nodes}
    assert len(supported) == 3


def test_support_off_the_nodes_still_reported():
    model, girder, _ = _girder_and_leg()
    girder.attributes["support_points"].append([1, 0.5, 0, "pinned"])  # off the axis: no node can match

    translator = TimberToStructural()
    translator.translate(model)

    assert "1 declared support point(s) matched no structural node and were ignored" in translator.report
