"""Switch on RFEM's timber design add-on for a pushed model (WP1).

What the add-on needs before ``calculate_all`` produces a ratio table -
found the hard way in the live session of 2026-09-18 (RFEM 6.13, dlubal.api
2.13.8) and written up in ``docs/discussion/roundtrip.md``:

1. the add-on flag and the EN 1995 standard in the base data;
2. a service class and a ULS configuration assigned to the timber members -
   RFEM creates no. 1 of each on activation, so they are *updated*;
3. a combination wizard that generates **load** combinations (the enum's
   ``True`` is result combinations, which no design add-on reads);
4. a ULS design situation bound to that wizard, then ``generate_combinations``;
5. the wizard's standard group set to "EN 1990 | Basis + Holz" - which the
   API neither exposes nor accepts, so it stays a one-time GUI step. Without
   it RFEM reports "some errors and warnings", an empty errors table and no
   design results; the reader's ``DESIGN_RESULTS_HINT`` says so.

Everything here is idempotent against a model that already has these
objects, because every run re-pushes the structure but not the base data.
"""

from dlubal.api import common


def _create_or_update(application, obj):
    """create_object, or update_object when RFEM says the number is taken."""
    try:
        application.create_object(obj)
        return "created"
    except Exception as error:  # the API raises a generic RpcError
        text = str(error)
        if "existiert bereits" in text or "already exists" in text:
            application.update_object(obj)
            return "updated"
        raise


def setup_timber_design(conn, structural_model, service_class=1, stability=False,
                        analysis_settings_no=1, wizard_no=1, design_situation_no=1):
    """Activate and configure the timber design add-on for the pushed model.

    Parameters
    ----------
    conn : DlubalClient
        An open connection.
    structural_model : StructuralModel
        The model that was just pushed; its BEAM members get the service class.
    service_class : int
        EN 1995 service class 1, 2 or 3 (``DesignAssumptions.service_class``).
    stability : bool
        Run RFEM's buckling / lateral-torsional checks. Off until WP1c
        supplies effective lengths - with the check on and no lengths the
        add-on fails silently.

    Returns
    -------
    dict
        What was set, for the log and the result metadata.
    """
    api = conn.api
    app = conn.application
    report = {"service_class": service_class, "stability": stability}

    # 1. base data: add-on, standard, combination wizard on, load combinations
    BaseData = api.base_data_pb2.BaseData
    base = app.get_base_data()
    base.addons.timber_design_active = True
    base.addons.combination_wizard_and_classification_active = True
    base.standards.timber_design_standard = BaseData.Standards.TimberDesignStandard.Value(
        "TIMBER_DESIGN_STANDARD_NATIONAL_ANNEX_AND_EDITION_EN_1995_CEN_2014_05_STANDARD")
    base.combinations_settings.combination_wizard_active = True
    base.combinations_settings.result_combinations_active = False
    app.set_base_data(base_data=base)
    base = app.get_base_data()
    report["timber_design_active"] = bool(base.addons.timber_design_active)
    report["timber_design_standard"] = BaseData.Standards.TimberDesignStandard.Name(base.standards.timber_design_standard)
    report["combination_wizard_standard"] = BaseData.Standards.CombinationWizardStandard.Name(base.standards.combination_wizard_standard)

    timber_members = [m.id for m in structural_model.members if getattr(m, "member_type", "BEAM") == "BEAM"]

    # 2. service class and ULS configuration (RFEM made no. 1 of each on activation)
    ServiceClass = api.timber_design.TimberServiceClass
    report["service_class_object"] = _create_or_update(app, ServiceClass(
        no=1, name="Service class {}".format(service_class), members=timber_members,
        service_class=getattr(ServiceClass.ServiceClass, "SERVICE_CLASS_{}".format(int(service_class)))))

    UlsConfiguration = api.timber_design_objects.TimberDesignUlsConfiguration
    report["uls_configuration"] = _create_or_update(app, UlsConfiguration(no=1, name="ULS", assigned_to_all_members=True))
    # The stability switch lives in the EC5 settings tree, which only exists
    # once RFEM has made the object - so read it back and update.
    existing = app.get_object(UlsConfiguration(no=1))
    tree = existing.settings_ec5
    common.tree_table.set_values_by_key(tree=tree, key="perform_stability_analysis", values=[bool(stability)])
    app.update_object(UlsConfiguration(no=1, settings_ec5=tree))

    # 3. combination wizard -> load combinations
    Wizard = api.loading.CombinationWizard
    report["combination_wizard"] = _create_or_update(app, Wizard(
        no=wizard_no, name="Tekton design", static_analysis_settings=analysis_settings_no,
        generate_combinations=Wizard.GenerateCombinations.GENERATE_COMBINATIONS_LOAD_COMBINATIONS))

    # 4. ULS design situation on that wizard, then the combinations
    DesignSituation = api.loading.DesignSituation
    report["design_situation"] = _create_or_update(app, DesignSituation(
        no=design_situation_no, name="ULS persistent/transient (6.10)",
        design_situation_type=DesignSituation.DesignSituationType.DESIGN_SITUATION_TYPE_STR_PERMANENT_AND_TRANSIENT_6_10,
        combination_wizard=wizard_no, active_for_timber_design=True))
    app.generate_combinations()

    situation = app.get_object(DesignSituation(no=design_situation_no))
    report["design_situation_active_for_timber"] = bool(situation.active_for_timber_design)
    # The one thing the API cannot fix (set_base_data ignores the field): the
    # wizard's standard group. RFEM exposes it in the enum name - "..._EN_1990_
    # BASE_TIMBER_DIN_..." is the GUI's "EN 1990 | Basis + Holz" with the DIN
    # annex - so at least it can be checked before the calculation hides it.
    if "TIMBER" not in report["combination_wizard_standard"] or not situation.active_for_timber_design:
        report["warning"] = (
            "the design situation is not active for timber design. Set the combination wizard's "
            "standard group to 'EN 1990 | Basis + Holz' in RFEM (Basisangaben > Normen > "
            "Lastkombinations-Assistent) - the API cannot - then run again.")
    return report



def disable_timber_design(conn):
    """Switch the timber design add-on (and the wizard) off if it is on.

    Base data survive ``delete_all_objects``; an active add-on whose
    configuration objects were just deleted makes ``calculate_all`` report
    "errors and warnings" and produce nothing (seen 2026-09-19 on the plate
    model, right after the sticks design run). One read, one write when
    needed.
    """
    app = conn.application
    base = app.get_base_data()
    if not (base.addons.timber_design_active or base.addons.combination_wizard_and_classification_active):
        return False
    base.addons.timber_design_active = False
    base.addons.combination_wizard_and_classification_active = False
    app.set_base_data(base_data=base)
    return True
