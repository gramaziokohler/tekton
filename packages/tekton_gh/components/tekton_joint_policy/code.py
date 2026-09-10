"""Tekton Joint Policy — Idealisierungsregel fuer Verbindungen.

Wie wird eine Holzverbindung mechanisch abgebildet: gelenkig, steif,
oder als Feder? Das ist eine Ingenieurentscheidung, die sich nicht aus
der Geometrie ableiten laesst — darum explizit, ueberschreibbar und im
Annahmenprotokoll dokumentiert.

'conservative' setzt alles gelenkig: die sichere Annahme fuer
Verformungen, aber sie unterschaetzt die Steifigkeit.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Joint Policy"  # type: ignore # noqa: F821


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
        raise RuntimeError("Tekton-Repo nicht gefunden — siehe TektonInfo.")
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
preset: str  # type: ignore
joint_types = joint_types  # type: ignore # noqa: F821
releases = releases  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.joint_policy import JointPolicy
from compas_timber_fea.core.releases import MemberRelease

PRESETS = {
    "conservative": JointPolicy.conservative,
    "rigid": JointPolicy.rigid,
    "catalogue": JointPolicy.default_catalogue,
}
RELEASES = {
    "rigid": MemberRelease.rigid,
    "pinned": MemberRelease.pinned,
    "spherical": MemberRelease.spherical,
}

key = (preset or "conservative").lower()
if key not in PRESETS:
    _warn("Unbekanntes Preset '{}'. Erlaubt: {}.".format(key, ", ".join(sorted(PRESETS))))
    key = "conservative"

policy = PRESETS[key]()
info = ["Preset: {} (Default: {})".format(key, policy.default.name)]

if joint_types and releases:
    if len(joint_types) != len(releases):
        _warn("joint_types ({}) und releases ({}) muessen gleich lang sein.".format(len(joint_types), len(releases)))
    else:
        for joint_type, release_name in zip(joint_types, releases):
            factory = RELEASES.get(str(release_name).lower())
            if factory is None:
                _warn("Unbekannte Freigabe '{}' fuer {}. Erlaubt: {}.".format(
                    release_name, joint_type, ", ".join(sorted(RELEASES))))
                continue
            policy.override_type(joint_type, factory())
            info.append("{} -> {}".format(joint_type, release_name))

for line in info:
    print(line)
