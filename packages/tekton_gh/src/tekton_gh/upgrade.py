"""Replace every Tekton component on the canvas with its installed template.

A UserObject is a template: an instance already placed keeps the script it
was created with. After a rebuild, the definition therefore has to be
re-populated - by hand from the ribbon, or by this. It reads the installed
``.ghuser`` files, and for every Tekton component in the document drops a
fresh instance at the same pivot, carries the wires over (inputs by
parameter name, outputs by parameter name to their recipients) and removes
the old instance.

Same rules as `rhino_io.attach_value_list`: the document is never touched
during a solve. The work is queued with ``ScheduleSolution`` and runs on the
UI thread after the current solve, guarded against the component having left
the document, and nothing escapes the callback - an exception there is a
silent crash of Rhino. The upgrade component never replaces itself.
"""

import os


def _store():
    """Per-process store that survives the component's module reload.

    The component reloads this module on every solve (so edits take effect
    without restarting Rhino), which wipes module globals - the report of
    the last upgrade and the "already queued" flag therefore live in
    scriptcontext.sticky, which Rhino keeps for the session.
    """
    try:
        import scriptcontext

        return scriptcontext.sticky.setdefault("tekton_upgrade", {})
    except Exception:  # outside Rhino (tests): a module-level dict will do
        return _FALLBACK


_FALLBACK = {}


def user_object_folder():
    """The Tekton subfolder of Grasshopper's UserObjects folder, or None."""
    import Grasshopper

    folders = list(Grasshopper.Folders.UserObjectFolders)
    for folder in folders:
        candidate = os.path.join(folder, "tekton")
        if os.path.isdir(candidate):
            return candidate
    return None


def installed_templates(folder):
    """{component name: path to .ghuser} for every template in ``folder``."""
    import Grasshopper

    templates = {}
    for fname in sorted(os.listdir(folder)):
        if not fname.lower().endswith(".ghuser"):
            continue
        path = os.path.join(folder, fname)
        try:
            uo = Grasshopper.Kernel.GH_UserObject(path)
            templates[uo.Description.Name] = path
        except Exception:
            continue
    return templates


def _swap(document, old, path):
    """Replace ``old`` with a fresh instance of the template at ``path``. Returns (carried, dropped)."""
    import Grasshopper
    from System.Drawing import PointF

    comp = Grasshopper.Kernel.GH_UserObject(path).InstantiateObject()
    comp.CreateAttributes()
    comp.Attributes.Pivot = PointF(old.Attributes.Pivot.X, old.Attributes.Pivot.Y)
    if old.NickName and old.NickName != comp.NickName:
        comp.NickName = old.NickName  # the user's naming survives

    sources = {p.Name: list(p.Sources) for p in old.Params.Input}
    recipients = [(r, p.Name) for p in old.Params.Output for r in list(p.Recipients)]
    hidden = getattr(old, "Hidden", False)

    document.RemoveObject(old, False)
    document.AddObject(comp, False)
    if hasattr(comp, "Hidden"):
        comp.Hidden = hidden

    carried = 0
    dropped = []
    new_inputs = {p.Name: p for p in comp.Params.Input}
    for name, srcs in sources.items():
        target = new_inputs.get(name)
        for src in srcs:
            if target is None:
                dropped.append("input '{}'".format(name))
                continue
            target.AddSource(src)
            carried += 1
    new_outputs = {p.Name: p for p in comp.Params.Output}
    for recipient, name in recipients:
        source = new_outputs.get(name)
        if source is None:
            dropped.append("output '{}'".format(name))
            continue
        recipient.AddSource(source)
        carried += 1
    return carried, dropped


def schedule_upgrade(ghenv, folder=None, only=None):
    """Queue the canvas-wide replacement. Returns (scheduled: bool, message: str).

    ``only``: optional set of component names to restrict to. The report of
    what happened is written to ``ghenv.Component`` as runtime remarks on the
    next solve, and returned via the ``report`` output of the component that
    reads ``last_report()``.
    """
    import Grasshopper

    component = ghenv.Component
    document = component.OnPingDocument()
    if document is None:
        return False, "no active document"
    folder = folder or user_object_folder()
    if not folder:
        return False, "Tekton UserObjects folder not found"
    templates = installed_templates(folder)
    if not templates:
        return False, "no .ghuser files in {}".format(folder)

    store = _store()
    key = str(component.InstanceGuid)
    if store.get(("pending", key)):
        return False, "an upgrade is already queued"

    def run(doc):
        report = []
        try:
            store.pop(("pending", key), None)
            if component.OnPingDocument() is None or not doc.Objects.Contains(component):
                return
            victims = [
                o for o in list(doc.Objects)
                if getattr(o, "Name", "") in templates
                and o.InstanceGuid != component.InstanceGuid
                and (not only or o.Name in only)
            ]
            for old in victims:
                try:
                    carried, dropped = _swap(doc, old, templates[old.Name])
                    line = "{} ({}): {} wires".format(old.Name, old.NickName, carried)
                    if dropped:
                        line += ", dropped " + ", ".join(dropped)
                    report.append(line)
                except Exception as exc:  # one bad swap must not stop the rest
                    report.append("{} ({}): FAILED {}".format(old.Name, old.NickName, exc))
            store[("report", key)] = report or ["nothing to upgrade"]
            component.ExpireSolution(False)
        except Exception as exc:
            store[("report", key)] = report + ["upgrade aborted: {}".format(exc)]

    delegate = Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(run)
    store[("pending", key)] = delegate
    document.ScheduleSolution(10, delegate)
    return True, "upgrade queued for {} templates".format(len(templates))


def last_report(ghenv):
    """The report of the last upgrade this component triggered, or []."""
    return list(_store().get(("report", str(ghenv.Component.InstanceGuid)), []))


__all__ = ["user_object_folder", "installed_templates", "schedule_upgrade", "last_report"]
