"""WP7: a grade per element instead of one for the whole model.

The bug this closes is quiet: the section library keyed sections by
dimensions alone, so a C24 joist and a GL24h beam of the same size shared
one section - and therefore one material. Every beam silently took the grade
of whichever was translated first, and nothing in the output looked wrong.
"""


from compas_timber.model import TimberModel

from tekton_core.translator import TimberToStructural

STICKS = "tests/timber_model_sticks.json"


def translated(assign=None, grade="C24"):
    """Translate the sticks model, optionally assigning grades to some beams."""
    model = TimberModel.from_json(STICKS)
    beams = list(model.beams)
    for index, value in (assign or {}).items():
        beams[index].attributes["material"] = value
    return TimberToStructural(material_name=grade, source_units="m").translate(model)


def sections_of(structural, material_id):
    return [s for s in structural.sections if s.material_id == material_id and s.name != "Rigid"]


# --- the default path stays what it was ---------------------------------

def test_without_assignments_there_is_one_material():
    structural = translated()
    assert len(structural.materials) == 1
    assert structural.materials[1].name == "C24"
    assert {s.material_id for s in structural.sections} == {1}


def test_the_model_wide_grade_still_applies():
    structural = translated(grade="GL28h")
    assert structural.materials[1].name == "GL28h"


# --- per-element grades --------------------------------------------------

def test_an_assigned_grade_becomes_its_own_material():
    structural = translated({0: "GL24h"})
    names = {m.name for m in structural.materials.values()}
    assert names == {"C24", "GL24h"}


def test_beams_of_the_same_size_but_different_grade_get_separate_sections():
    """The actual bug: one section for both meant one material for both."""
    structural = translated({0: "GL24h"})
    glulam = sections_of(structural, 2)
    solid = sections_of(structural, 1)
    assert glulam and solid
    # Same dimensions, two entries.
    assert any(
        abs(g.width - s.width) < 1e-9 and abs(g.height - s.height) < 1e-9
        for g in glulam for s in solid
    )


def test_the_section_name_records_which_material_it_belongs_to():
    structural = translated({0: "GL24h"})
    assert any(s.name.startswith("R_M2") for s in structural.sections)
    assert any(s.name.startswith("R_M1") for s in structural.sections)


def test_many_beams_of_one_grade_share_a_single_material():
    """Pooling by name: a hundred C24 beams are one material, not a hundred."""
    structural = translated({index: "GL24h" for index in range(20)})
    assert len(structural.materials) == 2


def test_an_unknown_grade_is_reported_not_silently_substituted():
    model = TimberModel.from_json(STICKS)
    list(model.beams)[0].attributes["material"] = "NotAGrade"
    translator = TimberToStructural(source_units="m")
    structural = translator.translate(model)
    assigned = [m for m in structural.materials.values() if m.name == "NotAGrade"]
    assert assigned and assigned[0].is_assumed
    assert any("NotAGrade" in line for line in translator.report)


def test_the_grade_attribute_is_accepted_as_well_as_material():
    model = TimberModel.from_json(STICKS)
    list(model.beams)[0].attributes["grade"] = "GL24h"
    structural = TimberToStructural(source_units="m").translate(model)
    assert {m.name for m in structural.materials.values()} == {"C24", "GL24h"}


def test_every_member_points_at_a_section_that_exists():
    structural = translated({0: "GL24h", 1: "GL28h"})
    section_ids = {s.id for s in structural.sections}
    for member in structural.members:
        assert member.section_id in section_ids


def test_every_section_points_at_a_material_that_exists():
    structural = translated({0: "GL24h", 1: "GL28h"})
    for section in structural.sections:
        assert section.material_id in structural.materials


def test_three_grades_yield_three_materials():
    structural = translated({0: "GL24h", 1: "GL28h", 2: "C30"})
    assert len(structural.materials) == 4        # C24 default + three assigned
    assert {m.name for m in structural.materials.values()} == {"C24", "GL24h", "GL28h", "C30"}


def test_material_properties_actually_differ():
    """A separate id is pointless if it carries the same numbers."""
    structural = translated({0: "GL24h"})
    solid = structural.materials[1]
    glulam = structural.materials[2]
    assert glulam.E0_mean != solid.E0_mean
    assert glulam.standard != solid.standard
