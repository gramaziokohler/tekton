"""The fingerprint: does a stamped result still describe the current model?

Results outliving a design change is the worst failure mode in this workflow -
a number on the canvas that looks current and answers a question about a model
that no longer exists. The fingerprint is what makes that visible, so it has
to be wrong in neither direction:

* a **false fresh** is dangerous: the model changed, the hash did not, and the
  stale numbers keep their authority. The GH-side placeholder hashed only
  geometry and topology, so changing a load magnitude or a timber grade left
  it identical.
* a **false stale** is merely annoying, but it trains people to ignore the
  warning - and the placeholder produced them too, because it hashed
  graph-order ids and unrounded floats.

Every test below is one of those two, named after the edit an engineer would
actually make.
"""

import math

from compas.geometry import Point
from compas.geometry import Vector

from compas_timber_fea.core.fingerprint import model_fingerprint
from compas_timber_fea.core.materials import Material
from compas_timber_fea.core.model import StructuralLoadCase
from compas_timber_fea.core.model import StructuralMember
from compas_timber_fea.core.model import StructuralMemberLoad
from compas_timber_fea.core.model import StructuralModel
from compas_timber_fea.core.model import StructuralNode
from compas_timber_fea.core.model import StructuralPointLoad
from compas_timber_fea.core.model import StructuralSection
from compas_timber_fea.core.model import StructuralSupport
from compas_timber_fea.core.model import StructuralSurface
from compas_timber_fea.core.model import StructuralSurfaceLoad
from compas_timber_fea.core.model import StructuralThickness
from compas_timber_fea.core.releases import LoadCombination
from compas_timber_fea.core.releases import MemberEccentricity
from compas_timber_fea.core.releases import MemberRelease


def _model():
    """A beam on two supports, one load case, one distributed load."""
    model = StructuralModel()
    model.materials[1] = Material(name="C24", f_mk=24.0)
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(4, 0, 0)))
    model.sections.append(StructuralSection(id=1, name="R 0.1/0.2", material_id=1, width=0.1, height=0.2))
    model.members.append(StructuralMember(id=1, node_start=1, node_end=2, section_id=1))
    model.supports.append(StructuralSupport(id=1, nodes=[1]))
    model.supports.append(StructuralSupport(id=2, nodes=[2], rx=0.0))
    model.load_cases.append(StructuralLoadCase(id=1, name="G", action_category="PERMANENT"))
    model.member_loads.append(StructuralMemberLoad(id=1, member_id=1, load_case_id=1, force=Vector(0, 0, -2.0)))
    return model


def _plate_model():
    model = StructuralModel()
    model.materials[1] = Material(name="C24")
    for i, p in enumerate([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], start=1):
        model.nodes.append(StructuralNode(id=i, point=Point(*p)))
    model.thicknesses.append(StructuralThickness(id=1, name="t", material_id=1, thickness=0.2))
    model.surfaces.append(StructuralSurface(id=1, nodes=[1, 2, 3, 4], thickness_id=1))
    model.supports.append(StructuralSupport(id=1, nodes=[1]))
    return model


# --- the fingerprint is a fingerprint ------------------------------------

def test_the_same_model_hashes_the_same_twice():
    assert model_fingerprint(_model()) == model_fingerprint(_model())


def test_it_is_short_enough_to_show_on_a_component():
    fingerprint = model_fingerprint(_model())
    assert len(fingerprint) == 12
    assert fingerprint.isalnum()


def test_an_empty_model_still_hashes():
    """No model is not an error here - Run stamps whatever it was given."""
    assert len(model_fingerprint(StructuralModel())) == 12


# --- false fresh: the model changed, so the hash must ---------------------
#
# Each of these was identical under the old geometry-only fingerprint.

def test_a_changed_load_magnitude_changes_it():
    model = _model()
    model.member_loads[0].force = Vector(0, 0, -3.0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_load_direction_changes_it():
    model = _model()
    model.member_loads[0].force = Vector(0, -2.0, 0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_load_extent_changes_it():
    """Half a span of load is not the same analysis as a full one."""
    model = _model()
    model.member_loads[0].dist_end = 0.5
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_timber_grade_changes_it():
    model = _model()
    model.materials[1] = Material(name="GL24h", f_mk=24.0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_strength_at_the_same_grade_name_changes_it():
    """The name is not the material - an edited property must count."""
    model = _model()
    model.materials[1] = Material(name="C24", f_mk=30.0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_an_added_load_case_changes_it():
    model = _model()
    model.load_cases.append(StructuralLoadCase(id=2, name="Q", action_category="VARIABLE"))
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_action_category_changes_it():
    """The category drives psi factors and k_mod - it is not a label."""
    model = _model()
    model.load_cases[0].action_category = "SNOW"
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_toggling_self_weight_changes_it():
    model = _model()
    model.load_cases[0].self_weight = True
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_combination_factor_changes_it():
    base = _model()
    base.load_combinations.append(LoadCombination(id=1000, name="ULS", factors={1: 1.35}))
    other = _model()
    other.load_combinations.append(LoadCombination(id=1000, name="ULS", factors={1: 1.5}))
    assert model_fingerprint(base) != model_fingerprint(other)


def test_an_added_point_load_changes_it():
    model = _model()
    model.point_loads.append(StructuralPointLoad(id=1, node_id=2, load_case_id=1, force=Vector(0, 0, -5)))
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_surface_load_changes_it():
    base = _plate_model()
    base.load_cases.append(StructuralLoadCase(id=1, name="G"))
    base.surface_loads.append(StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1.0)))
    other = _plate_model()
    other.load_cases.append(StructuralLoadCase(id=1, name="G"))
    other.surface_loads.append(StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -2.0)))
    assert model_fingerprint(base) != model_fingerprint(other)


def test_projecting_a_surface_load_changes_it():
    """Snow per m2 of plan is not snow per m2 of roof."""
    base = _plate_model()
    base.surface_loads.append(StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1)))
    other = _plate_model()
    other.surface_loads.append(
        StructuralSurfaceLoad(id=1, surface_id=1, load_case_id=1, pressure=Vector(0, 0, -1), projected=True)
    )
    assert model_fingerprint(base) != model_fingerprint(other)


def test_a_released_member_end_changes_it():
    """Pinning one end changes the moment diagram completely."""
    model = _model()
    model.members[0].release_start = MemberRelease(ry=0.0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_spring_stiffness_changes_it():
    base = _model()
    base.members[0].release_start = MemberRelease(ry=1000.0)
    other = _model()
    other.members[0].release_start = MemberRelease(ry=2000.0)
    assert model_fingerprint(base) != model_fingerprint(other)


def test_a_loosened_support_changes_it():
    model = _model()
    model.supports[0].uz = 0.0
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_orientation_vector_changes_it():
    """Rotating a beam swaps its strong and weak axis."""
    model = _model()
    model.members[0].orientation_vector = Vector(0, 1, 0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_an_eccentricity_changes_it():
    model = _model()
    model.members[0].eccentricity = MemberEccentricity(start=Vector(0, 0, 0.1))
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_section_changes_it():
    model = _model()
    model.sections[0].height = 0.3
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_thickness_changes_it():
    model = _plate_model()
    model.thicknesses[0].thickness = 0.24
    assert model_fingerprint(model) != model_fingerprint(_plate_model())


def test_an_added_opening_changes_it():
    model = _plate_model()
    for i, p in enumerate([(1, 1, 0), (2, 1, 0), (2, 2, 0), (1, 2, 0)], start=5):
        model.nodes.append(StructuralNode(id=i, point=Point(*p)))
    model.surfaces[0].openings = [[5, 6, 7, 8]]
    assert model_fingerprint(model) != model_fingerprint(_plate_model())


def test_a_changed_span_direction_changes_it():
    """CLT is markedly stiffer along the face grain - the direction is data."""
    model = _plate_model()
    model.surfaces[0].span_direction = Vector(1, 0, 0)
    assert model_fingerprint(model) != model_fingerprint(_plate_model())


def test_moving_a_node_changes_it():
    model = _model()
    model.nodes[1].point = Point(4.5, 0, 0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_a_changed_source_unit_changes_it():
    """The same numbers in mm and m are different structures."""
    model = _model()
    model.source_units = "mm"
    assert model_fingerprint(model) != model_fingerprint(_model())


# --- false stale: the model did not change, so the hash must not ----------

def test_renumbering_nodes_does_not_change_it():
    """The point of the whole exercise.

    Neutral ids come from graph order today (WP6), so an unrelated edit can
    renumber every node while the structure stands exactly where it stood.
    Hashing ids turned that into a 'results stale' warning that was not true.
    """
    base = _model()
    shifted = _model()
    for node in shifted.nodes:
        node.id += 100
    for member in shifted.members:
        member.node_start += 100
        member.node_end += 100
    for support in shifted.supports:
        support.nodes = [n + 100 for n in support.nodes]

    assert model_fingerprint(shifted) == model_fingerprint(base)


def test_renumbering_surfaces_does_not_change_it():
    base = _plate_model()
    shifted = _plate_model()
    for node in shifted.nodes:
        node.id += 50
    shifted.surfaces[0].nodes = [n + 50 for n in shifted.surfaces[0].nodes]
    shifted.supports[0].nodes = [n + 50 for n in shifted.supports[0].nodes]

    assert model_fingerprint(shifted) == model_fingerprint(base)


def test_float_noise_below_the_tolerance_does_not_change_it():
    """Coordinates pass through unit conversion and a solver round-trip.

    Unrounded floats meant the last bit of a division could flip the hash, so
    a model that was merely re-translated looked edited.
    """
    model = _model()
    model.nodes[1].point = Point(4.0 + 1e-11, 0, 0)
    assert model_fingerprint(model) == model_fingerprint(_model())


def test_a_move_worth_noticing_still_changes_it():
    """The tolerance must not swallow a real edit - 1 mm is a real edit."""
    model = _model()
    model.nodes[1].point = Point(4.001, 0, 0)
    assert model_fingerprint(model) != model_fingerprint(_model())


def test_reordering_the_member_list_does_not_change_it():
    """Iteration order of the structural graph is not a property of the model."""
    base = _model()
    base.members.append(StructuralMember(id=2, node_start=2, node_end=1, section_id=1))
    reordered = _model()
    reordered.members.append(StructuralMember(id=2, node_start=2, node_end=1, section_id=1))
    reordered.members.reverse()

    assert model_fingerprint(reordered) == model_fingerprint(base)


def test_reordering_load_cases_does_not_change_it():
    base = _model()
    base.load_cases.append(StructuralLoadCase(id=2, name="Q", action_category="VARIABLE"))
    reordered = _model()
    reordered.load_cases.append(StructuralLoadCase(id=2, name="Q", action_category="VARIABLE"))
    reordered.load_cases.reverse()

    assert model_fingerprint(reordered) == model_fingerprint(base)


def test_results_do_not_change_it():
    """A model with results in it is the same model - otherwise the stamp
    could never match the model it was computed from."""
    from compas_timber_fea.core.model import StructuralNodeResult
    from compas_timber_fea.core.model import StructuralResultSet

    model = _model()
    result_set = StructuralResultSet(load_case_id=1, name="LC1")
    result_set.node_results[1] = StructuralNodeResult(node_id=1, load_case_id=1, displacement=Vector(0, 0, -0.01))
    model.results[1] = result_set

    assert model_fingerprint(model) == model_fingerprint(_model())


def test_provenance_strings_do_not_change_it():
    """Source GUIDs say where a member came from, not what it does."""
    model = _model()
    model.members[0].source_element_id = "some-guid"
    model.members[0].source_segment_id = "some-guid:0"
    model.nodes[0].source_node_id = "17"
    assert model_fingerprint(model) == model_fingerprint(_model())


def test_a_material_given_as_a_bare_string_hashes_like_its_grade():
    """Older serialised models carry a grade name instead of a Material."""
    model = _model()
    model.materials[1] = "C24"
    assert len(model_fingerprint(model)) == 12


def test_infinite_stiffness_survives_hashing():
    """inf means rigid throughout the model and must be JSON-safe."""
    model = _model()
    model.supports[0].ux = math.inf
    assert len(model_fingerprint(model)) == 12


# --- malformed models still hash -----------------------------------------
#
# A model being debugged is the one most likely to be broken, and the
# fingerprint is part of debugging it. Sorting the payload entries directly
# raised here, because a dangling reference yields None next to a coordinate
# list and None < list is a TypeError.

def test_a_support_on_an_unknown_node_still_hashes():
    model = _model()
    model.supports[0].nodes = [1, 999]
    assert len(model_fingerprint(model)) == 12


def test_a_surface_on_unknown_nodes_still_hashes():
    model = _plate_model()
    model.surfaces[0].nodes = [1, 2, 77, 78]
    assert len(model_fingerprint(model)) == 12


def test_a_member_on_unknown_nodes_still_hashes():
    model = _model()
    model.members[0].node_start = 7
    assert len(model_fingerprint(model)) == 12


def test_a_load_on_an_unknown_member_still_hashes():
    model = _model()
    model.member_loads[0].member_id = 99
    assert len(model_fingerprint(model)) == 12


def test_a_load_on_an_unknown_surface_still_hashes():
    model = _plate_model()
    model.surface_loads.append(StructuralSurfaceLoad(id=1, surface_id=99, load_case_id=1, pressure=Vector(0, 0, -1)))
    assert len(model_fingerprint(model)) == 12


def test_the_payload_can_be_diffed():
    """Why the payload is public: when two models disagree, the answer to
    'which part changed' has to be inspectable, not just 'they differ'."""
    from compas_timber_fea.core.fingerprint import fingerprint_payload

    base = fingerprint_payload(_model())
    changed = _model()
    changed.member_loads[0].force = Vector(0, 0, -3.0)
    changed = fingerprint_payload(changed)

    differing = [key for key in base if base[key] != changed[key]]
    assert differing == ["member_loads"]
