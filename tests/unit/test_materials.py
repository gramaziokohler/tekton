"""The material library: a grade name is a key, not a material.

RFEM resolves names against its own library, but SAF wants numbers in the
sheet and OpenSees/Abaqus have no library at all - so the neutral model
carries the physical properties, with presets for the common grades.
"""

import pytest
from compas.geometry import Line
from compas_timber.elements import Beam
from compas_timber.model import TimberModel

from tekton_core.core.materials import PRESETS
from tekton_core.core.materials import Material
from tekton_core.core.model import StructuralModel
from tekton_core.translator import TimberToStructural


def test_presets_carry_full_physical_properties():
    c24 = Material.from_preset("C24")

    assert c24.E0_mean == 11000
    assert c24.density_mean == 420
    assert c24.G_mean == 690
    assert c24.f_mk == 24


def test_glulam_differs_from_solid_timber():
    """The whole point: GL24h must not silently get C24 stiffness."""
    c24 = Material.from_preset("C24")
    gl24h = Material.from_preset("GL24h")

    assert gl24h.E0_mean == 11500
    assert gl24h.E0_mean != c24.E0_mean
    assert gl24h.standard.startswith("EN 14080")
    assert c24.standard.startswith("EN 338")


def test_unknown_preset_raises_with_available_list():
    with pytest.raises(KeyError, match="Available presets"):
        Material.from_preset("Unobtainium")


def test_overrides_change_single_properties():
    softer = Material.from_preset("C24", E0_mean=10500)

    assert softer.E0_mean == 10500
    assert softer.density_mean == 420, "other properties must keep preset values"


def test_presets_are_copies_not_shared_state():
    first = Material.from_preset("C24")
    first.E0_mean = 1.0

    assert Material.from_preset("C24").E0_mean == 11000
    assert PRESETS["C24"].E0_mean == 11000


def test_resolve_passes_materials_through_and_upgrades_names():
    material = Material.from_preset("GL24h")

    assert Material.resolve(material) is material
    assert Material.resolve("C24").E0_mean == 11000


def test_resolve_of_unknown_grade_is_honest_not_silent():
    """Unknown grades borrow fallback properties but say so in the artifact."""
    mystery = Material.resolve("Eiche-Altbestand")

    assert mystery.name == "Eiche-Altbestand"
    assert mystery.E0_mean == 11000
    assert mystery.is_assumed
    assert "assumed as C24" in mystery.standard


def _translate(material_name):
    model = TimberModel()
    model.add_element(Beam.from_centerline(Line((0, 0, 0), (3, 0, 0)), width=0.1, height=0.2))
    translator = TimberToStructural(material_name=material_name)
    return translator, translator.translate(model)


def test_translator_puts_a_material_object_into_the_model():
    _translator, structural_model = _translate("GL24h")

    material = structural_model.materials[1]
    assert isinstance(material, Material)
    assert material.E0_mean == 11500


def test_translator_reports_assumed_materials():
    translator, structural_model = _translate("Fichte-irgendwas")

    assert structural_model.materials[1].is_assumed
    assert any("assumed" in entry for entry in translator.report)

    known_translator, _ = _translate("C24")
    assert not any("assumed" in entry for entry in known_translator.report)


def test_materials_survive_serialization(tmp_path):
    _translator, structural_model = _translate("GL28c")

    path = tmp_path / "model.json"
    structural_model.to_json(path)
    loaded = StructuralModel.from_json(path)

    material = loaded.materials[1]
    assert isinstance(material, Material)
    assert material.name == "GL28c"
    assert material.E0_mean == 12500


def test_legacy_string_materials_still_resolve():
    """Older serialized models carry plain name strings; consumers must cope."""
    model = StructuralModel()
    model.materials[1] = "C24"

    assert Material.resolve(model.materials[1]).density_mean == 420
