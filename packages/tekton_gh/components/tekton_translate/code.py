"""Tekton Translate — TimberModel -> neutrales StructuralModel.

Kern der Brücke. Erzeugt aus physischen Bauteilen ein mechanisches
Ersatzsystem: Systemlinien, Knoten, Querschnitte, Gelenke, Lager.

Der 'report'-Ausgang ist kein Debug-Output. Er listet die getroffenen
Idealisierungsannahmen — das, worüber der Statiker später diskutiert. Auf den
Canvas legen, nicht wegwerfen.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Translate"  # type: ignore # noqa: F821

# --------------------- INPUTS ---------------------
model = model  # type: ignore # noqa: F821  TimberModel
material = material  # type: ignore # noqa: F821
joint_policy = joint_policy  # type: ignore # noqa: F821
plate_policy = plate_policy  # type: ignore # noqa: F821
load_cases = load_cases  # type: ignore # noqa: F821
units: str  # type: ignore
repo: str  # type: ignore

# --------------------- SETUP ---------------------


def _setup(explicit_repo):
    """compas_timber_fea importierbar machen.

    In Rhino hat das offizielle COMPAS-Timber-Plugin womöglich schon eine
    andere Version geladen (1.0.5), die kein `compas_timber.structural`
    kennt. Deshalb Purge + Pfad-Priorität, nicht nur ein Append.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton-Repo nicht gefunden. Eine Komponente mit 'repo'-Input "
            "(TektonInfo, TektonTranslate, TektonBackend) einmal auf dem Canvas "
            "setzen — der Pfad gilt dann fuer die ganze Sitzung. Siehe TektonInfo."
        )
    # Fuer die Komponenten ohne eigenen repo-Input hinterlegen.
    os.environ["TEKTON_REPO"] = root

    for name in [m for m in list(sys.modules) if m.split(".")[0] in ("compas_timber", "compas_timber_fea", "tekton_gh")]:
        del sys.modules[name]

    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


# --------------------- SCRIPT ---------------------

structural = None
report = []
preview = []

if model is None:
    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        __import__("Grasshopper").Kernel.GH_RuntimeMessageLevel.Warning,
        "Kein TimberModel angeschlossen.",
    )
else:
    _setup(repo)

    from compas_timber_fea import TimberToStructural
    from compas_timber_fea.core.joint_policy import JointPolicy

    from tekton_gh.rhino_io import document_units, member_lines

    # Einheiten: das Modell kommt aus Rhino, ist also typisch mm; das neutrale
    # Modell rechnet in Metern. Ohne diese Uebersetzung wird ein mm-Modell
    # stumm zu einer 200-Meter-Platte.
    source_units = units or document_units(default="m")

    # TODO(scaffold): material ist heute nur ein Namens-String, den RFEM gegen
    # seine eigene Bibliothek aufloest. Sobald die Material-Dataclass mit
    # Presets existiert (discussion/materials.md), hier das Objekt durchreichen
    # und die Eigenschaften ins neutrale Modell schreiben.
    material_name = material if isinstance(material, str) else (getattr(material, "name", None) or "C24")

    policy = joint_policy if joint_policy is not None else JointPolicy.conservative()

    translator = TimberToStructural(
        material_name=material_name,
        source_units=source_units,
        joint_policy=policy,
        plate_policy=plate_policy,
        load_cases=list(load_cases) if load_cases else None,
    )

    structural = translator.translate(model)
    report = list(translator.report)

    # Tragrichtungs-Override aus der Plate Policy anwenden. Erst hier moeglich:
    # vor dem Uebersetzen gibt es keine Flaechen. Die Richtung entscheidet, wie
    # Plattenergebnisse zu lesen sind (RFEMs m_x folgt den Flaechenachsen), und
    # wird spaeter zu SurfaceRegion.frame.x im Plattengraph.
    override = getattr(plate_policy, "span_direction_override", None)
    if override and structural.surfaces:
        from compas.geometry import Vector

        for surface in structural.surfaces:
            surface.span_direction = Vector(*override)
        report.append(
            "Tragrichtung aller {} Flaechen auf ({:.3f}, {:.3f}, {:.3f}) gesetzt "
            "(Override aus der Plate Policy).".format(len(structural.surfaces), *override)
        )

    report.insert(0, "Einheiten des Timber-Modells: {}".format(source_units))
    report.insert(1, "Material (global): {}".format(material_name))
    if joint_policy is None:
        report.insert(2, "Verbindungen: konservativ (gelenkig) — keine Policy angeschlossen.")

    # Vorschau in Dokumenteinheiten: das neutrale Modell ist in Metern.
    scale = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(source_units, 1.0)
    preview = member_lines(structural, scale=scale)

    print("{} Knoten, {} Staebe, {} Flaechen, {} Lager".format(
        len(structural.nodes), len(structural.members),
        len(structural.surfaces), len(structural.supports)))

    if not structural.supports:
        import Grasshopper

        ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            "Modell hat keine Auflager. TektonSupport verwenden — sonst rechnet "
            "das Backend ein schwebendes System.",
        )
