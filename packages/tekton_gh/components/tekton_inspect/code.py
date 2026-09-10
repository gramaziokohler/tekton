"""Tekton Inspect — das Ersatzsystem selbst anschauen.

Systemlinien, Knoten, Lagersymbole, Gelenkmarker. Zum Pruefen der
Idealisierung, bevor gerechnet wird — bewusst getrennt von der
Ergebnisdarstellung.

Das ist die Ansicht, in der man sieht, ob die Idealisierung das
getan hat, was man erwartet hat: wo geteilt wurde, wo Gelenke sitzen.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Inspect"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """compas_timber_fea + tekton_gh importierbar machen.

    Siehe TektonInfo, wenn das fehlschlaegt. Der Purge ist noetig, weil in
    Rhino womoeglich schon ein anderes compas_timber geladen ist (das
    offizielle Plugin, 1.0.5), das kein `compas_timber.structural` kennt.
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
    for package in ("tekton_gh", "compas_timber_fea"):
        src = os.path.join(root, "packages", package, "src")
        if src in sys.path:
            sys.path.remove(src)
        sys.path.insert(0, src)
    return root


def _warn(message):
    import Grasshopper

    ghenv.Component.AddRuntimeMessage(  # type: ignore # noqa: F821
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message
    )

# --------------------- INPUTS ---------------------
structural = structural  # type: ignore # noqa: F821
show = show  # type: ignore # noqa: F821
scale: float  # type: ignore

# --------------------- SCRIPT ---------------------

members = []
nodes = []
supports = []
releases = []

if structural is None:
    _warn("Kein StructuralModel angeschlossen.")
else:
    _setup()
    import Rhino.Geometry as rg
    from tekton_gh.rhino_io import member_lines

    units = getattr(structural, "source_units", "m")
    factor = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}.get(units, 1.0)
    symbol = (scale if scale else 0.1) * factor

    wanted = set(s.lower() for s in (show or ["members", "nodes", "supports", "releases"]))
    node_points = {n.id: n.point for n in structural.nodes}

    if "members" in wanted:
        members = member_lines(structural, scale=factor)

    if "nodes" in wanted:
        nodes = [rg.Point3d(p[0] * factor, p[1] * factor, p[2] * factor) for p in node_points.values()]

    if "supports" in wanted:
        # Lager als kleines Achsenkreuz nach unten — reicht, um sie zu finden.
        for support in structural.supports:
            for node_id in support.nodes:
                point = node_points.get(node_id)
                if point is None:
                    continue
                base = rg.Point3d(point[0] * factor, point[1] * factor, point[2] * factor)
                tip = rg.Point3d(base.X, base.Y, base.Z - symbol)
                supports.append(rg.Line(base, tip))

    if "releases" in wanted:
        # Gelenke als kurzer Strich am Stabende, wo etwas freigegeben ist.
        for member in structural.members:
            start, end = node_points.get(member.node_start), node_points.get(member.node_end)
            if start is None or end is None:
                continue
            for release, anchor, other in ((member.release_start, start, end),
                                           (member.release_end, end, start)):
                if release is None or release.is_rigid():
                    continue
                ax = rg.Point3d(anchor[0] * factor, anchor[1] * factor, anchor[2] * factor)
                ox = rg.Point3d(other[0] * factor, other[1] * factor, other[2] * factor)
                direction = ox - ax
                if direction.Length == 0:
                    continue
                direction.Unitize()
                releases.append(rg.Line(ax, ax + direction * symbol * 0.5))

    print("{} Staebe, {} Knoten, {} Lager, {} Gelenkmarker".format(
        len(members), len(nodes), len(supports), len(releases)))
