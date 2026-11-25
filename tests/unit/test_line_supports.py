"""Line supports: a wall foot is not a row of point supports.

The distinction that makes this its own class: a nodal spring is kN/m, a line
spring is kN/m **per metre**. The same number means a different stiffness
depending on how finely the edge happens to be meshed, so the adapter has to
convert - and a refined mesh must not change the answer. That invariant is
what most of these tests check.

OpenSees has no line support at all, so the adapter distributes the stiffness
over the chain by tributary length. RFEM has a native object and takes the
per-metre values directly, which is why the neutral model stores per-metre.
"""

import math

import pytest

from compas.geometry import Point

from tekton_core.core.model import StructuralLineSupport
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralSurface
from tekton_core.core.model import StructuralThickness

INF = float("inf")


def _wall(length=4.0, spacing=1.0, stiffness=INF):
    """A chain of nodes along x, carrying one line support."""
    model = StructuralModel()
    count = int(round(length / spacing)) + 1
    for i in range(count):
        model.nodes.append(StructuralNode(id=i + 1, point=Point(i * spacing, 0, 0)))
    model.line_supports.append(
        StructuralLineSupport(id=1, nodes=[n.id for n in model.nodes], uz=stiffness)
    )
    return model


class RecordingOps:
    """Records the openseespy calls the builder makes, so the emission can
    be tested without openseespy installed."""

    def __init__(self):
        self.calls = []

    #: The one call whose return value the builder actually reads.
    STATIONS = [0.0, 0.25, 0.5, 0.75, 1.0]

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "sectionLocation":
                return list(self.STATIONS)
            return len(self.calls)
        return record

    def fixes(self):
        return [args for name, args, _ in self.calls if name == "fix"]

    def elements(self):
        return [args for name, args, _ in self.calls if name == "element"]


def _with_something_to_solve(model):
    """Add a free node and a member, so the builder has a live DOF.

    The builder refuses a model in which every DOF is fixed - rightly, since
    that aborts inside LAPACK rather than failing. A bare chain of supported
    nodes is not a model anyone would solve; a real wall foot carries a wall.
    """
    from tekton_core.core.model import StructuralMember
    from tekton_core.core.model import StructuralSection

    model.materials[1] = "C24"
    model.sections.append(StructuralSection(id=1, name="R", material_id=1, width=0.1, height=0.2))
    top = max(n.id for n in model.nodes) + 1
    model.nodes.append(StructuralNode(id=top, point=Point(0, 0, 3)))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=top, section_id=1))
    return model


def _build(model):
    from tekton_opensees.builder import ModelBuilder

    ops = RecordingOps()
    ModelBuilder(ops, _with_something_to_solve(model)).build()
    return ops



# --- the model ------------------------------------------------------------

def test_a_line_support_is_a_chain_of_nodes():
    support = _wall().line_supports[0]
    assert support.nodes == [1, 2, 3, 4, 5]


def test_it_is_rigid_by_default():
    """Same default as the nodal support: a declared support holds unless
    someone says otherwise."""
    support = StructuralLineSupport(id=1, nodes=[1, 2])
    assert (support.ux, support.uy, support.uz) == (INF, INF, INF)
    assert (support.rx, support.ry, support.rz) == (INF, INF, INF)


def test_a_model_has_none_by_default():
    assert StructuralModel().line_supports == []


def test_it_survives_the_json_round_trip():
    import os
    import tempfile

    from tekton_core.core.serialization import model_from_json
    from tekton_core.core.serialization import model_to_json

    model = _wall(stiffness=5000.0)
    model.line_supports[0].source_element_id = "plate-guid"
    model.line_supports[0].source_edge_index = 2

    path = os.path.join(tempfile.mkdtemp(), "m.json")
    model_to_json(model, path)
    restored = model_from_json(path).line_supports[0]

    assert restored.nodes == [1, 2, 3, 4, 5]
    assert restored.uz == 5000.0
    assert restored.source_element_id == "plate-guid"
    assert restored.source_edge_index == 2


def test_rigid_survives_the_json_round_trip():
    """inf has to come back as inf, not as a string or a huge float."""
    import os
    import tempfile

    from tekton_core.core.serialization import model_from_json
    from tekton_core.core.serialization import model_to_json

    path = os.path.join(tempfile.mkdtemp(), "m.json")
    model_to_json(_wall(), path)
    assert math.isinf(model_from_json(path).line_supports[0].uz)


# --- the fingerprint ------------------------------------------------------

def test_the_fingerprint_notices_a_line_support():
    from tekton_core.core.fingerprint import model_fingerprint

    without = _wall()
    without.line_supports = []
    assert model_fingerprint(_wall()) != model_fingerprint(without)


def test_the_fingerprint_notices_a_changed_line_stiffness():
    from tekton_core.core.fingerprint import model_fingerprint

    assert model_fingerprint(_wall(stiffness=5000.0)) != model_fingerprint(_wall(stiffness=9000.0))


def test_the_fingerprint_ignores_renumbering_of_a_line_support():
    from tekton_core.core.fingerprint import model_fingerprint

    base = _wall()
    shifted = _wall()
    for node in shifted.nodes:
        node.id += 100
    shifted.line_supports[0].nodes = [n + 100 for n in shifted.line_supports[0].nodes]

    assert model_fingerprint(shifted) == model_fingerprint(base)


# --- preflight ------------------------------------------------------------

def test_a_line_support_counts_as_restraint():
    """A plate held only along an edge is supported - preflight must not
    call it a mechanism just because there is no nodal support."""
    from tekton_core.core.preflight import preflight

    model = StructuralModel()
    model.materials[1] = "C24"
    for i, p in enumerate([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], start=1):
        model.nodes.append(StructuralNode(id=i, point=Point(*p)))
    model.thicknesses.append(StructuralThickness(id=1, name="t", material_id=1, thickness=0.2))
    model.surfaces.append(StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1))
    model.line_supports.append(StructuralLineSupport(id=1, nodes=[1, 2]))

    assert not any("support" in error.lower() for error in preflight(model).errors)


def test_a_line_support_of_one_node_is_an_error():
    """One node is a point support written in the wrong place."""
    from tekton_core.core.preflight import preflight

    model = _wall()
    model.line_supports[0].nodes = [1]

    report = preflight(model)
    assert any("line support" in message.lower() for message in report.errors + report.warnings)


def test_a_line_support_on_unknown_nodes_is_reported():
    from tekton_core.core.preflight import preflight

    model = _wall()
    model.line_supports[0].nodes = [1, 2, 999]

    report = preflight(model)
    assert any("line support" in message.lower() for message in report.errors + report.warnings)


# --- OpenSees: the per-metre conversion -----------------------------------

def test_a_rigid_line_support_fixes_every_node_on_it():
    ops = _build(_wall())
    fixed_nodes = {args[0] for args in ops.fixes()}
    assert {1, 2, 3, 4, 5} <= fixed_nodes


def test_a_rigid_line_support_holds_the_declared_directions():
    """uz rigid, everything else free by construction of the test wall."""
    model = _wall()
    model.line_supports[0].ux = 0.0
    model.line_supports[0].uy = 0.0
    model.line_supports[0].rx = 0.0
    model.line_supports[0].ry = 0.0
    model.line_supports[0].rz = 0.0

    ops = _build(model)
    for args in ops.fixes():
        assert args[1:] == (0, 0, 1, 0, 0, 0)


def test_a_springy_direction_becomes_a_spring_not_a_fix():
    """uz is finite, so it must not appear as a fixed DOF on a chain node -
    it is a zeroLength to a ghost instead. The other five stay rigid here,
    so those are still fixed."""
    ops = _build(_wall(stiffness=5000.0))
    chain = [args for args in ops.fixes() if args[0] in (1, 2, 3, 4, 5)]
    assert chain, "the chain nodes should still be fixed in the rigid directions"
    for args in chain:
        assert args[3] == 0, "uz is a spring, it must not be fixed as well"
    assert any("zeroLength" in str(args) for args in ops.elements())


def test_the_total_stiffness_is_length_times_the_per_metre_value():
    """The invariant. 4 m of 5000 kN/m2 is 20000 kN/m however it is meshed."""
    from tekton_opensees.builder import line_support_stiffnesses

    per_metre = 5000.0
    coarse = line_support_stiffnesses(_wall(spacing=2.0, stiffness=per_metre), 1)
    fine = line_support_stiffnesses(_wall(spacing=0.5, stiffness=per_metre), 1)

    assert sum(v["uz"] for v in coarse.values()) == pytest.approx(4.0 * per_metre)
    assert sum(v["uz"] for v in fine.values()) == pytest.approx(4.0 * per_metre)


def test_refining_the_mesh_does_not_change_the_total():
    from tekton_opensees.builder import line_support_stiffnesses

    totals = [
        sum(v["uz"] for v in line_support_stiffnesses(_wall(spacing=s, stiffness=1000.0), 1).values())
        for s in (2.0, 1.0, 0.5, 0.25)
    ]
    assert all(t == pytest.approx(totals[0]) for t in totals)


def test_the_end_nodes_carry_half_the_tributary_length():
    """A node in the middle owns half a segment on each side; an end node
    owns only one. Splitting it evenly would stiffen the ends."""
    from tekton_opensees.builder import line_support_stiffnesses

    values = line_support_stiffnesses(_wall(length=4.0, spacing=1.0, stiffness=1000.0), 1)
    assert values[1]["uz"] == pytest.approx(500.0)     # end: 0.5 m tributary
    assert values[3]["uz"] == pytest.approx(1000.0)    # middle: 1.0 m
    assert values[5]["uz"] == pytest.approx(500.0)     # end


def test_an_uneven_chain_weights_by_real_length():
    """Node spacing is not uniform once a mesher has been near it."""
    from tekton_opensees.builder import line_support_stiffnesses

    model = StructuralModel()
    for i, x in enumerate([0.0, 1.0, 5.0], start=1):
        model.nodes.append(StructuralNode(id=i, point=Point(x, 0, 0)))
    model.line_supports.append(StructuralLineSupport(id=1, nodes=[1, 2, 3], uz=100.0))

    values = line_support_stiffnesses(model, 1)
    assert values[1]["uz"] == pytest.approx(50.0)      # half of 1.0
    assert values[2]["uz"] == pytest.approx(250.0)     # half of 1.0 + half of 4.0
    assert values[3]["uz"] == pytest.approx(200.0)     # half of 4.0
    assert sum(v["uz"] for v in values.values()) == pytest.approx(5.0 * 100.0)


def test_a_rigid_direction_stays_rigid_per_node():
    """inf per metre is inf per node - multiplying it by a length is
    meaningless, and a rounding of inf would silently free the support."""
    from tekton_opensees.builder import line_support_stiffnesses

    model = _wall(stiffness=INF)
    model.line_supports[0].ux = 3000.0

    values = line_support_stiffnesses(model, 1)
    assert math.isinf(values[1]["uz"])
    assert math.isfinite(values[1]["ux"])


def test_a_free_direction_stays_free():
    from tekton_opensees.builder import line_support_stiffnesses

    model = _wall(stiffness=1000.0)
    model.line_supports[0].ux = 0.0

    assert line_support_stiffnesses(model, 1)[1]["ux"] == 0.0


def test_a_zero_length_chain_is_refused_rather_than_divided_by():
    """Two nodes in the same place have no length to distribute over."""
    from tekton_opensees.builder import line_support_stiffnesses

    model = StructuralModel()
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(0, 0, 0)))
    model.line_supports.append(StructuralLineSupport(id=1, nodes=[1, 2], uz=1000.0))

    with pytest.raises(ValueError, match="length"):
        line_support_stiffnesses(model, 1)


def test_a_broken_chain_is_a_warning_not_a_crash():
    """The builder keeps going and says what it skipped."""
    model = _wall()
    model.line_supports[0].nodes = [1, 2, 999]

    from tekton_opensees.builder import ModelBuilder

    ops = RecordingOps()
    built = ModelBuilder(ops, _with_something_to_solve(model)).build()
    warnings = built.warnings if hasattr(built, "warnings") else []
    assert any("line support" in w for w in warnings)


def test_a_line_and_a_nodal_support_on_one_node_both_apply():
    """They are different objects; the node is simply held by both.

    The line here holds uz only, the nodal support holds everything, so the
    node ends up with two fix calls rather than one silently replacing the
    other."""
    from tekton_core.core.model import StructuralSupport

    model = _wall(stiffness=INF)
    for dof in ("ux", "uy", "rx", "ry", "rz"):
        setattr(model.line_supports[0], dof, 0.0)
    model.supports.append(StructuralSupport(id=1, nodes=[1]))

    ops = _build(model)
    on_node_one = [args for args in ops.fixes() if args[0] == 1]
    assert len(on_node_one) == 2, on_node_one
    assert (0, 0, 1, 0, 0, 0) in [args[1:] for args in on_node_one]


# --- authoring: the two ways to declare one -------------------------------

def _timber_plate(attributes=None):
    """A 4x4 plate, optionally carrying supported-edge attributes."""
    from compas.geometry import Polyline
    from compas_timber.elements import Plate
    from compas_timber.model import TimberModel

    t = 0.2
    outline_a = Polyline([Point(0, 0, 0), Point(4, 0, 0), Point(4, 4, 0), Point(0, 4, 0), Point(0, 0, 0)])
    outline_b = Polyline([Point(0, 0, t), Point(4, 0, t), Point(4, 4, t), Point(0, 4, t), Point(0, 0, t)])
    plate = Plate.from_outlines(outline_a, outline_b)
    for key, value in (attributes or {}).items():
        plate.attributes[key] = value
    model = TimberModel()
    model.add_element(plate)
    return model


def _translate(timber_model):
    from tekton_core.translator import TimberToStructural

    return TimberToStructural(source_units="m").translate(timber_model)


def test_an_edge_index_becomes_a_line_support():
    structural = _translate(_timber_plate({"supported_edges": [0]}))

    assert len(structural.line_supports) == 1
    assert len(structural.line_supports[0].nodes) == 2


def test_the_edge_index_is_kept_for_traceability():
    structural = _translate(_timber_plate({"supported_edges": [2]}))
    support = structural.line_supports[0]

    assert support.source_edge_index == 2
    assert support.source_element_id


def test_several_edges_become_several_supports():
    structural = _translate(_timber_plate({"supported_edges": [0, 2]}))
    assert len(structural.line_supports) == 2
    assert {s.source_edge_index for s in structural.line_supports} == {0, 2}


def test_an_edge_can_carry_a_support_type():
    structural = _translate(_timber_plate({"supported_edges": [[0, "roller"]]}))
    support = structural.line_supports[0]

    assert support.uz == INF
    assert support.ux == 0.0     # a roller is free horizontally
    assert "roller" in support.name


def test_an_unknown_support_type_falls_back_and_says_so():
    from tekton_core.translator import TimberToStructural

    translator = TimberToStructural(source_units="m")
    structural = translator.translate(_timber_plate({"supported_edges": [[0, "nonsense"]]}))

    assert structural.line_supports[0].ux == INF        # pinned
    assert any("pinned" in line for line in translator.report)


def test_an_edge_index_out_of_range_is_reported_not_dropped():
    from tekton_core.translator import TimberToStructural

    translator = TimberToStructural(source_units="m")
    structural = translator.translate(_timber_plate({"supported_edges": [99]}))

    assert structural.line_supports == []
    assert any("matched no surface edge" in line for line in translator.report)


def test_a_plate_without_declared_edges_gets_none():
    assert _translate(_timber_plate()).line_supports == []


def test_a_support_line_is_matched_onto_an_edge():
    """The other authoring route: a curve, matched by midpoint."""
    structural = _translate(_timber_plate({
        "support_lines": [[(0, 0, 0), (4, 0, 0)]],
    }))

    assert len(structural.line_supports) == 1
    assert structural.line_supports[0].source_edge_index == 0


def test_a_support_line_can_carry_a_type():
    structural = _translate(_timber_plate({
        "support_lines": [[(0, 0, 0), (4, 0, 0), "fixed"]],
    }))
    support = structural.line_supports[0]

    assert support.rx == INF and support.ry == INF
    assert "fixed" in support.name


def test_a_support_line_that_matches_nothing_is_ignored():
    """Same failure mode as the support points, and just as visible."""
    structural = _translate(_timber_plate({
        "support_lines": [[(99, 99, 0), (99, 100, 0)]],
    }))
    assert structural.line_supports == []


def test_the_chain_uses_the_surface_nodes():
    """Conformity: the support sits on the same node ids as the plate, so a
    mesh cannot separate them."""
    structural = _translate(_timber_plate({"supported_edges": [0]}))
    surface_nodes = set(structural.surfaces[0].nodes)

    assert set(structural.line_supports[0].nodes) <= surface_nodes


def test_a_supported_plate_passes_preflight():
    from tekton_core.core.preflight import preflight

    structural = _translate(_timber_plate({"supported_edges": [0]}))
    assert not any("no supports" in error for error in preflight(structural).errors)
