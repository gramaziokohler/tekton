"""Model view specs: which symbol for which support, where loads and reactions point."""

import os
import sys

from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralNodeResult
from compas_timber_fea.core.model import StructuralPointLoad
from compas_timber_fea.core.model import StructuralResultSet
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.releases import MemberRelease

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "tekton_gh", "src"))

from tekton_gh.model_view import COLOURS  # noqa: E402
from tekton_gh.model_view import connection_specs  # noqa: E402
from tekton_gh.model_view import element_specs  # noqa: E402
from tekton_gh.model_view import legend  # noqa: E402
from tekton_gh.model_view import load_specs  # noqa: E402
from tekton_gh.model_view import reaction_specs  # noqa: E402
from tekton_gh.model_view import support_kind  # noqa: E402
from tekton_gh.model_view import support_label  # noqa: E402
from tekton_gh.model_view import support_specs  # noqa: E402

INF = float("inf")


def support(**kw):
    return StructuralSupport(id=1, nodes=[1], **kw)


def test_support_classification_from_stiffnesses():
    assert support_kind(support())[0] == "fixed"
    assert support_kind(support(rx=0.0, ry=0.0, rz=0.0))[0] == "pinned"
    kind, free, _, _ = support_kind(support(ux=0.0, rx=0.0, ry=0.0, rz=0.0))
    assert (kind, free) == ("roller", ["x"])
    assert support_kind(support(ux=0.0, uy=0.0, rx=0.0, ry=0.0, rz=0.0))[0] == "ball"
    assert support_kind(support(rx=0.0))[0] == "partial"
    assert support_kind(support(rx=0.0, ry=0.0))[0] == "partial"  # a ball-jointed clamp, not "pinned"
    assert "spring" in support_label(support(rx=0.0, ry=0.0, rz=1500.0))


def _model():
    m = StructuralModel()
    m.nodes = [StructuralNode(id=1, point=Point(0, 0, 0)), StructuralNode(id=2, point=Point(2, 0, 0)), StructuralNode(id=3, point=Point(2, 0.05, 0))]
    m.sections = [StructuralSection(id=1, name="R", material_id=1, width=0.1, height=0.2), StructuralSection(id=2, name="Rigid", material_id=1, width=0, height=0)]
    m.members = [
        StructuralMember(id=1, node_start=1, node_end=2, section_id=1, member_type="BEAM", source_element_id="A"),
        StructuralMember(id=2, node_start=2, node_end=3, section_id=2, member_type="COUPLING", release_end=MemberRelease.pinned(), source_element_type="connector"),
    ]
    m.supports = [StructuralSupport(id=1, nodes=[1], rx=0.0, ry=0.0, rz=0.0)]
    m.load_cases = [StructuralLoadCase(id=1, name="LC1", action_category="PERMANENT", self_weight=True)]
    m.point_loads = [StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -4.0))]
    m.member_loads = [StructuralMemberLoad(id=1, member_id=1, load_case_id=1, force=Vector(0, 0, -2.0))]
    return m


def test_pinned_support_is_pyramid_on_plate_with_label():
    """All rotations free: the bare pyramid, apex at the node, plate below, label."""
    specs = support_specs(_model(), scale=1000.0, size=0.1)

    kinds = [s["kind"] for s in specs]
    assert kinds == ["pyramid", "plate", "text"]
    assert specs[0]["apex"] == Point(0, 0, 0)
    assert specs[0]["size"] == 100.0  # 0.1 m in a mm document
    assert specs[1]["point"].z == -100.0  # plate at the pyramid base
    assert specs[2]["text"] == "pinned"


def test_one_free_rotation_is_a_cylinder_along_that_axis():
    m = _model()
    m.supports = [StructuralSupport(id=1, nodes=[1], ry=0.0)]  # only phi_y free

    specs = support_specs(m)

    cyl = next(s for s in specs if s["kind"] == "cylinder")
    assert list(cyl["axis"]) == [0.0, 1.0, 0.0]
    assert cyl["point"] == Point(0, 0, 0)  # at the apex


def test_two_free_rotations_are_a_sphere():
    m = _model()
    m.supports = [StructuralSupport(id=1, nodes=[1], rx=0.0, ry=0.0)]

    specs = support_specs(m)

    assert [s["kind"] for s in specs] == ["pyramid", "sphere", "plate", "text"]


def test_all_rotations_fixed_has_no_pyramid():
    m = _model()
    m.supports = [StructuralSupport(id=1, nodes=[1], ux=0.0, uy=0.0)]  # uz + all rotations fixed, sliding

    specs = support_specs(m)

    kinds = [s["kind"] for s in specs]
    assert "pyramid" not in kinds
    assert kinds.count("plate") == 2  # plate sliding on plate: two free translations


def test_roller_adds_rails_along_the_free_direction():
    m = _model()
    m.supports = [StructuralSupport(id=1, nodes=[1], ux=0.0, rx=0.0, ry=0.0, rz=0.0)]

    specs = support_specs(m)

    rails = [s for s in specs if s["kind"] == "rod"]
    assert len(rails) == 2
    for rail in rails:
        assert rail["start"].y != rail["end"].y or rail["start"].x != rail["end"].x
        assert abs(rail["end"].x - rail["start"].x) > 0 and rail["start"].y == rail["end"].y  # along x
    assert rails[0]["start"].y < 0 < rails[1]["start"].y  # spread across


def test_rotational_clamp_without_translations_is_bars():
    m = _model()
    m.supports = [StructuralSupport(id=1, nodes=[1], ux=0.0, uy=0.0, uz=0.0, rx=0.0, ry=0.0)]  # only phi_z fixed

    specs = support_specs(m)

    kinds = [s["kind"] for s in specs]
    assert kinds == ["rod", "text"]
    bar = specs[0]
    assert bar["start"].z < 0 < bar["end"].z  # along z


def test_connections_show_coupling_and_its_hinge():
    specs = connection_specs(_model())

    rods = [s for s in specs if s["kind"] == "rod"]
    spheres = [s for s in specs if s["kind"] == "sphere"]
    assert len(rods) == 1 and rods[0]["colour"] == COLOURS["coupling"]
    assert len(spheres) == 1 and spheres[0]["point"] == Point(2, 0.05, 0)  # hinged end only
    assert spheres[0]["label"].startswith("hinge")


def test_connector_thickness_is_capped_by_its_length():
    """A 5 cm coupling must not become a 5 cm thick blob: diameter <= length / 3."""
    specs = connection_specs(_model(), size=0.15)

    rod = next(s for s in specs if s["kind"] == "rod")
    hinge = next(s for s in specs if s["kind"] == "sphere" and s["colour"] == COLOURS["hinge"])
    assert rod["radius"] * 2 <= 0.05 / 3 + 1e-9
    assert hinge["radius"] <= 0.05 / 3 + 1e-9


def test_loads_point_at_the_node_and_scale_with_magnitude():
    specs = load_specs(_model(), load_case_id=1, per_kn=0.5)

    arrows = [s for s in specs if s["kind"] == "arrow"]
    point_arrow = next(s for s in arrows if s.get("label") == "4 kN")
    assert point_arrow["end"] == Point(2, 0, 0)
    assert point_arrow["start"].z == 2.0  # 4 kN * 0.5 m/kN, coming from above
    assert len(arrows) > 1  # the member load row
    assert any(s["kind"] == "text" and s["text"] == "2 kN/m" for s in specs)
    assert load_specs(_model(), load_case_id=2) == []


def test_reactions_only_with_results():
    m = _model()
    assert reaction_specs(m) == []
    m.results[1] = StructuralResultSet(load_case_id=1, node_results={1: StructuralNodeResult(node_id=1, load_case_id=1, reaction_force=Vector(0, 0, 6.0))})

    specs = reaction_specs(m)

    assert len(specs) == 1 and specs[0]["colour"] == COLOURS["reaction"]
    assert specs[0]["end"] == Point(0, 0, 0)
    assert "6 kN" in specs[0]["label"]


def test_elements_skip_sectionless_members():
    specs = element_specs(_model())

    assert len(specs) == 1
    assert specs[0]["width"] == 0.1


def test_legend_counts():
    lines = legend(_model(), load_case_id=1)

    assert lines[0] == "Members: 1 beam, 1 coupling"
    assert lines[1] == "Supports: 1x pinned"
    assert lines[2] == "Loads LC1: 1 point, 1 member"
    assert lines[3] == "Self-weight: LC1"
