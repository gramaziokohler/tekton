"""Area loads on beam grids, and beam-relative line load ranges.

The anchor for the area load is conservation: whatever rule hands a panel's
load to its edges, the line loads times their lengths must add up to pressure
times loaded area. If that holds, nothing was lost or counted twice; the
rule only decides how it is shared.
"""

import math

import pytest

from compas.geometry import Point

from tekton_core.core.load_distribution import distribute_area_load
from tekton_core.core.load_distribution import edge_widths
from tekton_core.core.load_distribution import element_ranges
from tekton_core.core.load_distribution import find_panels
from tekton_core.core.load_distribution import point_in_regions
from tekton_core.core.load_distribution import split_range
from tekton_core.core.model import StructuralMember
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode


def grid(nx, ny, dx=1.0, dy=1.0, z=0.0, legs=()):
    """A beam grid split at every crossing, as the translator leaves it.

    `legs` are (i, j) grid nodes that get an inclined member down to z - 3,
    standing in for the diagonals of the HIL roof.
    """
    model = StructuralModel()
    ids = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            ids[i, j] = len(model.nodes) + 1
            model.nodes.append(StructuralNode(id=ids[i, j], point=Point(i * dx, j * dy, z)))
    member = 0
    for i in range(nx + 1):
        for j in range(ny + 1):
            for di, dj, source in ((1, 0, "x%d" % j), (0, 1, "y%d" % i)):
                if (i + di, j + dj) in ids:
                    member += 1
                    model.members.append(StructuralMember(
                        id=member, node_start=ids[i, j], node_end=ids[i + di, j + dj],
                        section_id=1, source_element_id=source))
    for i, j in legs:
        node = len(model.nodes) + 1
        model.nodes.append(StructuralNode(id=node, point=Point(i * dx - 1.0, j * dy, z - 3.0)))
        member += 1
        model.members.append(StructuralMember(id=member, node_start=node, node_end=ids[i, j], section_id=1))
    return model


def lengths(model):
    nodes = {n.id: n.point for n in model.nodes}
    return {m.id: math.dist(nodes[m.node_start], nodes[m.node_end]) for m in model.members}


def total(model, loads):
    length = lengths(model)
    return sum(-f[2] * length[i] for i, f in loads.items())


# --- panels -------------------------------------------------------------------

def test_a_grid_has_one_panel_per_field():
    model = grid(3, 2)
    edges = [(m.id, model.nodes[m.node_start - 1].point, model.nodes[m.node_end - 1].point) for m in model.members]

    panels, pruned = find_panels(edges)

    assert len(panels) == 6
    assert pruned == 0
    assert all(len(p["edges"]) == 4 for p in panels)


def test_a_dangling_beam_frames_no_field():
    model = grid(1, 1)
    edges = [(m.id, model.nodes[m.node_start - 1].point, model.nodes[m.node_end - 1].point) for m in model.members]
    edges.append((99, (1.0, 1.0, 0.0), (2.0, 1.0, 0.0)))

    panels, pruned = find_panels(edges)

    assert len(panels) == 1
    assert pruned == 1


# --- sharing out a panel ----------------------------------------------------------

def test_a_square_panel_gives_a_quarter_side_to_each_edge():
    panel = {"points": [(0, 0), (4, 0), (4, 4), (0, 4)],
             "edges": [(1, (0, 0), (4, 0)), (2, (4, 0), (4, 4)), (3, (4, 4), (0, 4)), (4, (0, 4), (0, 0))]}

    widths, rule = edge_widths(panel)

    assert rule == "45deg"
    assert widths == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_a_rectangle_follows_the_45_degree_rule():
    """Short side: the triangle s^2/4; long side: the trapezoid."""
    panel = {"points": [(0, 0), (6, 0), (6, 2), (0, 2)],
             "edges": [(1, (0, 0), (6, 0)), (2, (6, 0), (6, 2)), (3, (6, 2), (0, 2)), (4, (0, 2), (0, 0))]}

    widths, _ = edge_widths(panel)

    short = 2 * 2 / 4.0 / 2       # triangle s^2/4 over its length s
    long = (12 - 2 * 1.0) / 2 / 6  # (area - both triangles) / 2, over 6
    assert widths == pytest.approx([long, short, long, short])
    assert sum(w * l for w, l in zip(widths, (6, 2, 6, 2))) == pytest.approx(12.0)


def test_a_split_edge_carries_the_same_load_on_both_pieces():
    """A T-joint in the middle of a field edge must not change the share."""
    panel = {"points": [(0, 0), (2, 0), (4, 0), (4, 4), (0, 4)],
             "edges": [(1, (0, 0), (2, 0)), (5, (2, 0), (4, 0)), (2, (4, 0), (4, 4)),
                       (3, (4, 4), (0, 4)), (4, (0, 4), (0, 0))]}

    widths, rule = edge_widths(panel)

    assert rule == "45deg"
    assert widths == pytest.approx([1.0, 1.0, 1.0, 1.0, 1.0])


def test_a_triangle_uses_the_centroid_rule_and_keeps_the_total():
    panel = {"points": [(0, 0), (3, 0), (0, 3)],
             "edges": [(1, (0, 0), (3, 0)), (2, (3, 0), (0, 3)), (3, (0, 3), (0, 0))]}

    widths, rule = edge_widths(panel)

    assert rule == "centroid"
    sides = (3.0, math.hypot(3, 3), 3.0)
    assert sum(w * l for w, l in zip(widths, sides)) == pytest.approx(4.5)


# --- the whole load ---------------------------------------------------------------

def test_the_total_is_pressure_times_area():
    model = grid(4, 3, dx=4.81, dy=4.81, z=24.4)

    loads, info = distribute_area_load(model, (0, 0, -3.0))

    area = 4 * 3 * 4.81 ** 2
    assert info["panels_loaded"] == 12
    assert info["area"] == pytest.approx(area)
    assert total(model, loads) == pytest.approx(3.0 * area)


def test_an_inner_member_carries_two_quarter_fields():
    model = grid(2, 1, dx=4.0, dy=4.0)

    loads, _ = distribute_area_load(model, (0, 0, -2.0))

    # The middle cross beam (x=4) frames both fields: 2 * q*l/4.
    middle = [m for m in model.members if m.source_element_id == "y1"][0]
    assert loads[middle.id][2] == pytest.approx(-2.0 * 4.0 / 2)


def test_the_load_goes_downward_as_given():
    model = grid(1, 1)

    loads, _ = distribute_area_load(model, (0, 0, -1.0))

    assert all(f[0] == 0 and f[1] == 0 and f[2] < 0 for f in loads.values())


def test_only_the_highest_level_is_loaded_by_default():
    model = grid(1, 1, z=0.0)
    upper = grid(1, 1, z=5.0)
    offset = len(model.nodes)
    for n in upper.nodes:
        model.nodes.append(StructuralNode(id=n.id + offset, point=n.point))
    for m in upper.members:
        model.members.append(StructuralMember(id=m.id + 100, node_start=m.node_start + offset,
                                              node_end=m.node_end + offset, section_id=1))

    loads, info = distribute_area_load(model, (0, 0, -1.0))

    assert info["level"] == pytest.approx(5.0)
    assert all(i > 100 for i in loads)


def test_a_ring_region_loads_only_the_canopy():
    """Outline plus inner curve: even-odd makes the ring between them."""
    model = grid(4, 4)
    outline = [(-0.5, -0.5), (4.5, -0.5), (4.5, 4.5), (-0.5, 4.5)]
    inner = [(1, 1), (3, 1), (3, 3), (1, 3)]

    _, ring = distribute_area_load(model, (0, 0, -1.0), regions=[outline, inner])
    _, middle = distribute_area_load(model, (0, 0, -1.0), regions=[inner])

    assert ring["panels_loaded"] == 12
    assert middle["panels_loaded"] == 4
    assert ring["area"] + middle["area"] == pytest.approx(16.0)


def test_rigid_links_are_not_part_of_the_grid():
    model = grid(1, 1)
    model.members[0].member_type = "RIGID"

    _, info = distribute_area_load(model, (0, 0, -1.0))

    assert info["panels"] == 0


def test_inclined_members_do_not_frame_panels():
    model = grid(2, 2, legs=[(1, 1)])

    _, info = distribute_area_load(model, (0, 0, -1.0))

    assert info["panels"] == 4


# --- regions ------------------------------------------------------------------------

def test_point_in_regions_is_even_odd():
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]
    hole = [(1, 1), (3, 1), (3, 3), (1, 3)]

    assert point_in_regions((0.5, 0.5), [square, hole])
    assert not point_in_regions((2, 2), [square, hole])
    assert not point_in_regions((5, 5), [square, hole])


# --- beam-relative ranges ----------------------------------------------------------

def test_a_range_on_a_split_beam_lands_on_the_right_pieces():
    """0.25..0.5 of a beam split into four: the second piece, whole."""
    model = grid(4, 0)
    beam = [m.id for m in model.members if m.source_element_id == "x0"]

    pieces = split_range(element_ranges(model, beam), 0.25, 0.5)

    assert pieces == [(beam[1], 0.0, 1.0)]


def test_a_range_may_cut_a_piece():
    model = grid(4, 0)
    beam = [m.id for m in model.members if m.source_element_id == "x0"]

    pieces = split_range(element_ranges(model, beam), 0.1, 0.3)

    assert pieces == [(beam[0], pytest.approx(0.4), 1.0), (beam[1], 0.0, pytest.approx(0.2))]


def test_a_reversed_piece_is_measured_from_its_own_start():
    model = grid(2, 0)
    beam = [m.id for m in model.members if m.source_element_id == "x0"]
    second = [m for m in model.members if m.id == beam[1]][0]
    second.node_start, second.node_end = second.node_end, second.node_start

    pieces = dict((i, (a, b)) for i, a, b in split_range(element_ranges(model, beam), 0.5, 0.75))

    assert pieces[beam[1]] == (pytest.approx(0.5), 1.0)
