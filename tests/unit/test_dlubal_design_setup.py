"""The timber design add-on setup, offline against an Application stub.

The stub uses the real dlubal.api.rfem message classes, so the object
types, enum names and field names the setup relies on are checked against
the pinned wheel; only the gRPC calls are faked. What the live session found
(2026-09-18) is pinned here: update-not-create for the auto-created objects,
load combinations (not result combinations) from the wizard, and the
warning when the wizard's standard group is not the timber one.
"""

import pytest

rfem = pytest.importorskip("dlubal.api.rfem", reason="dlubal-api not installed")

from compas_dlubal.dlubal.design_setup import setup_timber_design  # noqa: E402


class Member:
    def __init__(self, member_id, member_type="BEAM"):
        self.id = member_id
        self.member_type = member_type


class Model:
    def __init__(self):
        self.members = [Member(1), Member(2), Member(3, "RIGID")]


class ApplicationStub:
    """Remembers objects by (type, no); refuses a second create like RFEM does."""

    def __init__(self, wizard_standard="COMBINATION_WIZARD_NATIONAL_ANNEX_AND_EDITION_EN_1990_BASE_TIMBER_DIN_2012_08_STANDARD",
                 preexisting=()):
        self.base = rfem.BaseData()
        self.base.standards.combination_wizard_standard = (
            rfem.BaseData.Standards.CombinationWizardStandard.Value(wizard_standard))
        self.objects = {}
        self.calls = []
        for obj in preexisting:
            self.objects[(type(obj).__name__, obj.no)] = obj

    def get_base_data(self, **_):
        return self.base

    def set_base_data(self, *, base_data, **_):
        self.calls.append("set_base_data")
        self.base = base_data

    def create_object(self, obj, **_):
        key = (type(obj).__name__, obj.no)
        if key in self.objects:
            raise RuntimeError("Failed to create {} No. {}.  {} Nr. {} existiert bereits.".format(*key, *key))
        self.calls.append("create " + key[0])
        self.objects[key] = obj
        self._after_create(obj)

    def update_object(self, obj, **_):
        key = (type(obj).__name__, obj.no)
        assert key in self.objects, key
        self.calls.append("update " + key[0])
        self.objects[key].MergeFrom(obj)

    def get_object(self, obj, **_):
        key = (type(obj).__name__, obj.no)
        if key not in self.objects:
            raise RuntimeError("{} Nr. {} existiert nicht.".format(*key))
        return self.objects[key]

    def generate_combinations(self, **_):
        self.calls.append("generate_combinations")
        situation = self.objects.get(("DesignSituation", 1))
        if situation is not None:
            timber = "TIMBER" in rfem.BaseData.Standards.CombinationWizardStandard.Name(
                self.base.standards.combination_wizard_standard)
            situation.active_for_timber_design = timber

    def _after_create(self, obj):
        # RFEM fills the EC5 settings tree of a new ULS configuration itself.
        if isinstance(obj, rfem.timber_design_objects.TimberDesignUlsConfiguration):
            row = obj.settings_ec5.rows.add()
            row.key = "allgemeine_optionen"
            leaf = row.rows.add()
            leaf.key = "perform_stability_analysis"
            leaf.value.bool_value = True


class Conn:
    def __init__(self, application):
        self.api = rfem
        self.application = application


def test_fresh_model_gets_the_full_setup():
    app = ApplicationStub()
    report = setup_timber_design(Conn(app), Model(), service_class=2)

    assert app.base.addons.timber_design_active
    assert app.base.combinations_settings.combination_wizard_active
    assert not app.base.combinations_settings.result_combinations_active

    service_class = app.objects[("TimberServiceClass", 1)]
    assert list(service_class.members) == [1, 2]  # the rigid member carries no timber
    assert service_class.service_class == rfem.timber_design.TimberServiceClass.ServiceClass.SERVICE_CLASS_2

    uls = app.objects[("TimberDesignUlsConfiguration", 1)]
    assert uls.assigned_to_all_members
    assert uls.settings_ec5.rows[0].rows[0].value.bool_value is False  # stability off until WP1c

    wizard = app.objects[("CombinationWizard", 1)]
    assert wizard.generate_combinations == rfem.loading.CombinationWizard.GenerateCombinations.GENERATE_COMBINATIONS_LOAD_COMBINATIONS

    situation = app.objects[("DesignSituation", 1)]
    assert situation.combination_wizard == 1
    assert "generate_combinations" in app.calls
    assert report["design_situation_active_for_timber"] is True
    assert "warning" not in report


def test_auto_created_objects_are_updated_not_recreated():
    """Activating the add-on makes service class 1 and ULS configuration 1 - a second create fails."""
    preexisting = [
        rfem.timber_design.TimberServiceClass(no=1),
        rfem.timber_design_objects.TimberDesignUlsConfiguration(no=1),
    ]
    app = ApplicationStub(preexisting=preexisting)
    app._after_create(preexisting[1])
    report = setup_timber_design(Conn(app), Model())

    assert report["service_class_object"] == "updated"
    assert report["uls_configuration"] == "updated"
    assert list(app.objects[("TimberServiceClass", 1)].members) == [1, 2]


def test_wrong_wizard_standard_is_reported_with_the_gui_step():
    app = ApplicationStub(wizard_standard="COMBINATION_WIZARD_NATIONAL_ANNEX_AND_EDITION_EN_1990_DIN_2012_08_STANDARD")
    report = setup_timber_design(Conn(app), Model())

    assert report["design_situation_active_for_timber"] is False
    assert "Basis + Holz" in report["warning"]
