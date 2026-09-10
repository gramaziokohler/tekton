"""Tekton Material Library — Gütekasse auswählen statt tippen.

Hängt sich beim ersten Solve selbst ein Auswahlmenü an den `grade`-Eingang,
gefüllt aus `compas_timber_fea.core.materials.PRESETS`. Damit ist die
Bibliothek die Quelle der Auswahl: kommt ein Preset dazu, steht es im Menü,
ohne dass hier etwas nachgezogen wird.

Ohne Auswahl listet die Komponente auf, was es gibt — sie ist dann ein
Nachschlagewerk, keine Fehlermeldung.

Für Überschreibungen einzelner Kennwerte ist **TektonMaterial** zuständig;
diese hier ist der schnelle Griff ins Regal.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Material Library"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea importierbar machen."""
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
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def attach_value_list(names):
    """Ein Auswahlmenue an den 'grade'-Eingang haengen, falls dort nichts haengt.

    Das ist das Bedienmuster, das man von Karamba kennt: Komponente
    platzieren, Menue ist da. Ohne das muesste man die Gueteklasse als Text
    tippen — fehleranfaellig und ohne Uebersicht.

    **Der Canvas darf waehrend eines Solves nicht veraendert werden.** Ein
    ``doc.AddObject`` mitten im Solve — erst recht zusammen mit
    ``ExpireSolution`` — bringt Rhino zum Absturz (hier passiert, 2026-09-10).
    Deshalb wird die Arbeit ueber ``ScheduleSolution`` in einen Rueckruf
    gelegt, der laeuft, wenn der aktuelle Solve fertig ist.

    Nur wenn der Eingang frei ist: eine bestehende Verkabelung zu ueberschreiben
    waere uebergriffig.
    """
    import Grasshopper as gh
    import System

    component = ghenv.Component  # type: ignore # noqa: F821
    param = component.Params.Input[0]
    if param.SourceCount:
        return False

    doc = component.OnPingDocument()
    if doc is None:
        return False

    def build(gh_document):
        # Zweite Pruefung: zwischen Planung und Ausfuehrung kann der Nutzer
        # laengst selbst etwas angehaengt haben.
        if param.SourceCount:
            return
        value_list = gh.Kernel.Special.GH_ValueList()
        value_list.CreateAttributes()
        value_list.Name = "Grade"
        value_list.NickName = "Grade"
        value_list.ListItems.Clear()
        for name in names:
            value_list.ListItems.Add(
                gh.Kernel.Special.GH_ValueListItem(name, '"{}"'.format(name))
            )
        value_list.SelectItem(0)

        # Links neben den Eingang setzen, damit das Kabel nicht kreuzt.
        pivot = component.Attributes.Pivot
        bounds = value_list.Attributes.Bounds
        value_list.Attributes.Pivot = System.Drawing.PointF(
            float(pivot.X - bounds.Width - 90), float(pivot.Y - 10)
        )
        gh_document.AddObject(value_list, False)
        param.AddSource(value_list)
        param.ExpireSolution(False)

    doc.ScheduleSolution(10, gh.Kernel.GH_Document.GH_ScheduleDelegate(build))
    return True


# --------------------- INPUTS ---------------------
grade: str  # type: ignore

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.materials import PRESETS, Material  # noqa: E402

grades = sorted(PRESETS)

# Beim ersten Solve das Menue planen. Es entsteht nach diesem Solve; der
# davon ausgeloeste naechste Solve laeuft dann mit gewaehlter Guete durch.
attach_value_list(grades)

material = None
properties = []

name = (grade or "").strip().strip('"')
if not name:
    properties = ["{} Gueteklassen verfuegbar:".format(len(grades))]
    for key in grades:
        preset = PRESETS[key]
        properties.append("  {:<7} E0 {:>6.0f} N/mm2   rho {:>3.0f} kg/m3   {}".format(
            key, preset.E0_mean, preset.density_mean, preset.standard))
    properties.append("")
    properties.append("Eine Gueteklasse waehlen, um ein Material auszugeben.")
else:
    material = Material.resolve(name)
    if material.is_assumed:
        import Grasshopper

        ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            "Unbekannte Guete '{}'. Eigenschaften von C24 uebernommen und als "
            "Annahme markiert.".format(name),
        )
    properties = [
        "{} ({})".format(material.name, material.standard),
        "E0,mean   {:>7.0f} N/mm2".format(material.E0_mean),
        "E0,k      {:>7.0f} N/mm2".format(material.E0_k),
        "E90,mean  {:>7.0f} N/mm2".format(material.E90_mean),
        "G,mean    {:>7.0f} N/mm2".format(material.G_mean),
        "rho,mean  {:>7.0f} kg/m3".format(material.density_mean),
        "rho,k     {:>7.0f} kg/m3".format(material.density_k),
        "f_m,k     {:>7.1f} N/mm2".format(material.f_mk),
        "f_t0,k    {:>7.1f} N/mm2".format(material.f_t0k),
        "f_c0,k    {:>7.1f} N/mm2".format(material.f_c0k),
        "f_v,k     {:>7.1f} N/mm2".format(material.f_vk),
    ]

for line in properties:
    print(line)
