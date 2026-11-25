"""Conformance tests for the SAF exporter.

SAF is a Z-up format (like COMPAS), so the neutral model must be written out
without the Z-down conventions of the Dlubal backend.
"""

import pandas as pd
import pytest
from compas.geometry import Point
from compas.geometry import Vector

from tekton_saf.exporter.saf import SAFExporter
from tekton_core.core.model import StructuralMember
from tekton_core.core.model import StructuralModel
from tekton_core.core.model import StructuralNode
from tekton_core.core.model import StructuralSection
from tekton_core.core.model import StructuralSupport

# Valid enum values per the SAF specification (saf.guide).
SAF_SUPPORT_TYPES = {"Fixed", "Hinged", "Sliding", "Custom"}
SAF_TRANSLATION_CONSTRAINTS = {
    "Rigid",
    "Free",
    "Flexible",
    "Compression only",
    "Tension only",
    "Flexible compression only",
    "Flexible tension only",
    "Non linear",
}
SAF_ROTATION_CONSTRAINTS = {"Free", "Rigid", "Flexible", "Non linear"}


@pytest.fixture
def column_model():
    """A single vertical column from z=0 to z=3, supported at its base."""
    model = StructuralModel()
    model.materials[1] = "C24"
    model.nodes.append(StructuralNode(id=1, point=Point(0, 0, 0)))
    model.nodes.append(StructuralNode(id=2, point=Point(0, 0, 3)))
    model.sections.append(StructuralSection(id=1, name="R_M1 0.1/0.2", width=0.1, height=0.2, shape_type="rectangular", material_id=1))
    model.members.append(
        StructuralMember(
            id=1,
            node_start=1,
            node_end=2,
            section_id=1,
            orientation_vector=Vector(0, 1, 0),
            source_element_id="beam-guid-1",
            source_element_type="beam",
        )
    )
    model.supports.append(
        StructuralSupport(
            id=1,
            nodes=[1],
            name="Base",
            ux=float("inf"),
            uy=float("inf"),
            uz=float("inf"),
            rx=0.0,
            ry=0.0,
            rz=0.0,
        )
    )
    return model


def _sheet(path, name):
    return pd.read_excel(path, sheet_name=name)


@pytest.fixture
def exported(column_model, tmp_path):
    path = tmp_path / "model.xlsx"
    assert SAFExporter(column_model).export(str(path)) is not False
    return path


def test_z_coordinates_are_not_inverted(exported):
    """SAF is Z-up: a column at z=3 must not be exported at z=-3."""
    nodes = _sheet(exported, "StructuralPointConnection")

    z_values = sorted(float(z) for z in nodes["Coordinate Z [m]"])
    assert z_values == [0.0, 3.0]


def test_support_enums_are_spec_conformant(exported):
    supports = _sheet(exported, "StructuralPointSupport")

    assert not supports.empty, "support rows are missing"
    row = supports.iloc[0]
    assert row["Type"] in SAF_SUPPORT_TYPES
    for dof in ("ux", "uy", "uz"):
        assert row[dof] in SAF_TRANSLATION_CONSTRAINTS
    for dof in ("fix", "fiy", "fiz"):
        assert row[dof] in SAF_ROTATION_CONSTRAINTS


def test_fixed_translations_are_rigid_and_free_rotations_are_free(exported):
    supports = _sheet(exported, "StructuralPointSupport")
    row = supports.iloc[0]

    assert row["ux"] == "Rigid"
    assert row["uy"] == "Rigid"
    assert row["uz"] == "Rigid"
    assert row["fix"] == "Free"


def test_member_lcs_vector_is_written(exported):
    """With LCS 'y by vector' the coordinate columns must carry the local-y vector."""
    members = _sheet(exported, "StructuralCurveMember")
    row = members.iloc[0]

    vector = (row["Coordinate X [m]"], row["Coordinate Y [m]"], row["Coordinate Z [m]"])
    assert any(abs(float(c)) > 0 for c in vector), "LCS vector is (0,0,0), which defines no direction"
    assert (float(row["Coordinate X [m]"]), float(row["Coordinate Y [m]"]), float(row["Coordinate Z [m]"])) == (0.0, 1.0, 0.0)


def test_empty_sheets_still_have_headers(column_model, tmp_path):
    """A model without supports must still produce a valid, header-bearing sheet."""
    column_model.supports = []
    path = tmp_path / "no_supports.xlsx"
    SAFExporter(column_model).export(str(path))

    supports = _sheet(path, "StructuralPointSupport")
    assert list(supports.columns), "sheet was written without a header row"
    assert supports.empty


def test_section_dimensions_are_rounded_not_truncated(tmp_path):
    """0.115 m must become 115 mm, not 114."""
    model = StructuralModel()
    model.materials[1] = "C24"
    model.sections.append(StructuralSection(id=1, name="R_M1 0.115/0.2", width=0.115, height=0.2, shape_type="rectangular", material_id=1))

    path = tmp_path / "sections.xlsx"
    SAFExporter(model).export(str(path))

    sections = _sheet(path, "StructuralCrossSection")
    assert sections.iloc[0]["Parameters [mm]"].startswith("115;")


def test_load_case_attributes_come_from_the_model(column_model, tmp_path):
    """Action type and load type must reflect the case, not a hardcoded default."""
    from tekton_core.core.model import StructuralLoadCase

    column_model.load_cases.append(StructuralLoadCase(id=1, name="Self-Weight", action_category="PERMANENT", self_weight=True))
    column_model.load_cases.append(StructuralLoadCase(id=2, name="Snow", action_category="SNOW"))

    path = tmp_path / "loads.xlsx"
    SAFExporter(column_model).export(str(path))
    cases = _sheet(path, "StructuralLoadCase")

    self_weight = cases[cases["Name"] == "Self-Weight"].iloc[0]
    snow = cases[cases["Name"] == "Snow"].iloc[0]

    assert self_weight["Action type"] == "Permanent"
    assert snow["Action type"] == "Variable"
    # SAF spells it without a hyphen, and only self-weight cases may use it.
    assert self_weight["Load type"] == "Self weight"
    assert snow["Load type"] != "Self weight"


def test_material_properties_come_from_the_material(column_model, tmp_path):
    """A GL24h model must not export with C24 stiffness."""
    from tekton_core.core.materials import Material

    column_model.materials[1] = Material.from_preset("GL24h")

    path = tmp_path / "materials.xlsx"
    SAFExporter(column_model).export(str(path))
    materials = _sheet(path, "StructuralMaterial")

    row = materials.iloc[0]
    assert row["Quality"] == "GL24h"
    assert float(row["E modulus [MPa]"]) == 11500.0
    assert float(row["Unit mass [kg/m3]"]) == 420.0
    assert float(row["G modulus [MPa]"]) == 650.0


def test_legacy_string_material_still_exports_with_real_properties(column_model, tmp_path):
    """The fixture stores the grade as a plain string - it must still resolve."""
    path = tmp_path / "legacy.xlsx"
    SAFExporter(column_model).export(str(path))
    materials = _sheet(path, "StructuralMaterial")

    row = materials.iloc[0]
    assert row["Quality"] == "C24"
    assert float(row["E modulus [MPa]"]) == 11000.0
