"""Tekton Joint Policy - idealisation rule for joints.

How is a timber joint represented mechanically: pinned, rigid, or as a spring?
That is an engineering decision which cannot be derived from the geometry -
hence explicit, overridable, and documented in the assumptions report.

'conservative' makes everything pinned: the safe assumption for deflections,
but it underestimates the stiffness.
"""
# venv: tekton-test
# r: compas, compas_timber

import os
import sys

ghenv.Component.Message = "Joint Policy"  # type: ignore # noqa: F821


def _setup(explicit_repo=None):
    """Make compas_timber_fea + tekton_gh importable.

    See TektonInfo when this fails. The purge is needed because Rhino may
    already have another compas_timber loaded (the official plugin, 1.0.5),
    which knows no `compas_timber.structural`.
    """
    root = None
    for candidate in (explicit_repo, os.environ.get("TEKTON_REPO")):
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), "packages")):
            root = os.path.expanduser(candidate)
            break
    if root is None:
        raise RuntimeError(
            "Tekton repo not found. Place one component with a 'repo' input "
            "(TektonInfo, TektonTranslate, TektonBackend) on the canvas once - "
            "the path then applies for the whole session. See TektonInfo."
        )
    # Deposit it for the components without a repo input of their own.
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
preset: str  # type: ignore
joint_types = joint_types  # type: ignore # noqa: F821
releases = releases  # type: ignore # noqa: F821

# --------------------- SCRIPT ---------------------

_setup()
from compas_timber_fea.core.joint_policy import JointPolicy
from compas_timber_fea.core.releases import MemberRelease

from tekton_gh.rhino_io import value_list_items

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

key = (preset or "conservative").lower().strip('"')
if key not in PRESETS:
    _warn("Unknown preset '{}'. Allowed: {}.".format(key, ", ".join(sorted(PRESETS))))
    key = "conservative"

policy = PRESETS[key]()
info = list(value_list_items(ghenv, sorted(PRESETS)))  # type: ignore # noqa: F821
info.append("Preset: {} (default: {})".format(key, policy.default.name))

if joint_types and releases:
    if len(joint_types) != len(releases):
        _warn("joint_types ({}) and releases ({}) must be the same length.".format(len(joint_types), len(releases)))
    else:
        for joint_type, release_name in zip(joint_types, releases):
            factory = RELEASES.get(str(release_name).lower())
            if factory is None:
                _warn("Unknown release '{}' for {}. Allowed: {}.".format(
                    release_name, joint_type, ", ".join(sorted(RELEASES))))
                continue
            policy.override_type(joint_type, factory())
            info.append("{} -> {}".format(joint_type, release_name))

for line in info:
    print(line)
