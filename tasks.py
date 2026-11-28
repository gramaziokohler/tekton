"""Release tasks (invoke). Install with ``uv sync --extra dev --extra release``.

    uv run invoke --list
    uv run invoke bump --part patch          # all packages, one version
    uv run invoke check-release              # the pre-tag checks
    uv run invoke gh-headers --release       # component headers for a release build
    uv run invoke build-ghuser               # .ghuser files (Windows, pythonnet)
    uv run invoke yakerize                   # dist/yak_package/tekton-X.Y.Z-rh8-any.yak
    uv run invoke publish-yak -y <file.yak> --test-server

The order and the reasons are in docs/RELEASE.md. yakerize and publish-yak
come from compas_invocations2, like in the other COMPAS projects; the rest is
Tekton-specific because the repo is a monorepo (seven pyproject files, one
version) and the components live in a sub-package.
"""

import os
import platform
import re
import subprocess
import sys

from compas_invocations2 import grasshopper
from invoke import Collection
from invoke import Exit
from invoke import task

HERE = os.path.dirname(os.path.abspath(__file__))
GH_PACKAGE = os.path.join(HERE, "packages", "tekton_gh")
COMPONENTS = os.path.join(GH_PACKAGE, "components")
COMPONENTIZER = os.path.join(GH_PACKAGE, "_componentizer")
GHUSER_BUILD = os.path.join(COMPONENTIZER, "ghuser_build")

#: What every component header says, by mode. Development components find the
#: monorepo on disk and keep their own Rhino venv, so a released Tekton and a
#: checkout never share an environment. A release names one PyPI package;
#: tekton-gh pulls in tekton_core, which pulls in compas_timber.
DEV_VENV = "tekton-test"
DEV_REQUIREMENTS = "compas, compas_timber"
RELEASE_VENV = "tekton"
RELEASE_PACKAGE = "tekton-gh"

HEADER_VENV = re.compile(r"^# venv:.*$", re.M)
HEADER_R = re.compile(r"^# r:.*$", re.M)


def current_version():
    """The one version, from [tool.bumpversion] in the root pyproject."""
    with open(os.path.join(HERE, "pyproject.toml"), encoding="utf-8") as handle:
        match = re.search(r'^\[tool\.bumpversion\]\s*\ncurrent_version = "([^"]+)"', handle.read(), re.M)
    if not match:
        raise Exit("No [tool.bumpversion] current_version in pyproject.toml.")
    return match.group(1)


@task(help={"part": "major, minor or patch"})
def bump(ctx, part):
    """Raise the version of every package at once and refresh uv.lock."""
    if part not in ("major", "minor", "patch"):
        raise Exit("part must be one of major, minor, patch")
    ctx.run("bump-my-version bump {}".format(part), pty=False)
    ctx.run("uv lock", pty=False)
    print("Now at {}. Next: CHANGELOG.md, then `invoke check-release`.".format(current_version()))


@task(
    help={
        "release": "Write the release header (# r: tekton-gh>=VERSION, # venv: tekton).",
        "version": "Version for the release header. Default: the current version.",
    }
)
def gh_headers(ctx, release=False, version=None):
    """Rewrite the `# r:` and `# venv:` lines of every component, in place.

    The source stays in development mode on purpose; the publish workflow
    runs this with --release on its own checkout just before the build.
    Unlike compas_invocations2's update_gh_header it rewrites the lines where
    they are (after the docstring) and takes the package from tekton_gh,
    not from the root project, which is not published.
    """
    if release:
        version = version or current_version()
        venv_line = "# venv: {}".format(RELEASE_VENV)
        r_line = "# r: {}>={}".format(RELEASE_PACKAGE, version)
    else:
        venv_line = "# venv: {}".format(DEV_VENV)
        r_line = "# r: {}".format(DEV_REQUIREMENTS)

    changed = 0
    for name in sorted(os.listdir(COMPONENTS)):
        path = os.path.join(COMPONENTS, name, "code.py")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", newline="") as handle:
            source = handle.read()
        if len(HEADER_VENV.findall(source)) != 1 or len(HEADER_R.findall(source)) != 1:
            raise Exit("{}: expected exactly one '# venv:' and one '# r:' line".format(path))
        updated = HEADER_R.sub(r_line, HEADER_VENV.sub(venv_line, source))
        if updated != source:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
            changed += 1
    print("{} components: {} / {} ({} changed)".format("release" if release else "dev", r_line, venv_line, changed))


@task(help={"version": "Written into the components. Default: the current version."})
def build_ghuser(ctx, version=None):
    """Build the .ghuser files into packages/tekton_gh/_componentizer/ghuser_build.

    Windows only: the componentizer loads GH_IO.dll through pythonnet and
    needs no Rhino. On macOS it has to run inside Rhino instead - see
    install.py --build or _componentizer/componetize.bash.
    """
    if platform.system() != "Windows":
        raise Exit("build-ghuser runs on Windows (pythonnet + GH_IO.dll). On macOS use: python3 install.py --fix --build")
    version = version or current_version()
    if os.path.isdir(GHUSER_BUILD):
        for name in os.listdir(GHUSER_BUILD):
            if name.endswith(".ghuser"):
                os.remove(os.path.join(GHUSER_BUILD, name))
    subprocess.run([sys.executable, os.path.join(COMPONENTIZER, "build_metadata.py")], check=True, cwd=GH_PACKAGE)
    subprocess.run(
        [sys.executable, os.path.join(COMPONENTIZER, "componentize_cpy.py"), COMPONENTS, GHUSER_BUILD, "--version", version],
        check=True,
        cwd=COMPONENTIZER,
    )
    built = [n for n in os.listdir(GHUSER_BUILD) if n.endswith(".ghuser")]
    expected = [n for n in os.listdir(COMPONENTS) if os.path.isfile(os.path.join(COMPONENTS, n, "code.py"))]
    if len(built) != len(expected):
        raise Exit("Built {} of {} components - see _componentizer/componentizer.log".format(len(built), len(expected)))
    print("Built {} components ({}).".format(len(built), version))


#: Patterns that must never reach a release. The ghx path panels are the known
#: offender: Grasshopper writes the absolute repo path back on every save.
FORBIDDEN = (
    (r"/Users/[^/\s\"'<]+/", "a macOS home directory"),
    (r"[A-Za-z]:\\\\?Users\\\\?[^\\\s\"'<]+", "a Windows home directory"),
    (r"Mobile Documents", "an iCloud path"),
    (r"ak-[A-Za-z0-9]{20,}", "a Dlubal API key"),
)


@task
def check_release(ctx):
    """The checks before tagging: versions agree, no paths or keys, lint, tests."""
    version = current_version()
    problems = []

    for name in sorted(os.listdir(os.path.join(HERE, "packages"))):
        path = os.path.join(HERE, "packages", name, "pyproject.toml")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                found = re.search(r'^version = "([^"]+)"', handle.read(), re.M)
            if not found or found.group(1) != version:
                problems.append("{}: version {} != {}".format(path, found and found.group(1), version))

    tracked = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True, text=True, check=True).stdout.split("\n")
    for relative in tracked:
        if not relative.endswith((".py", ".ghx", ".json", ".md", ".toml", ".yml", ".txt")):
            continue
        if relative in ("tasks.py",):
            continue
        try:
            with open(os.path.join(HERE, relative), encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        for pattern, what in FORBIDDEN:
            hit = re.search(pattern, text)
            if hit and "/Users/user/" not in hit.group(0) and "Users\\user" not in hit.group(0):
                problems.append("{}: {} ({})".format(relative, what, hit.group(0)[:60]))

    for problem in problems:
        print("  FAIL " + problem)
    if problems:
        raise Exit("{} problem(s) - fix them before tagging.".format(len(problems)))
    print("  ok   versions: all {}".format(version))
    print("  ok   no user paths or keys in tracked files")
    ctx.run("ruff check .", pty=False)
    ctx.run("pytest -q", pty=False)


ns = Collection(
    bump,
    check_release,
    gh_headers,
    build_ghuser,
    grasshopper.yakerize,
    grasshopper.publish_yak,
)
ns.configure(
    {
        "base_folder": HERE,
        "ghuser_cpython": {
            "source_dir": "packages/tekton_gh/components",
            "target_dir": "packages/tekton_gh/_componentizer/ghuser_build",
        },
        "yak": {
            "manifest_path": "packages/tekton_gh/yak_template/manifest.yml",
            "logo_path": "packages/tekton_gh/yak_template/icon.png",
        },
    }
)
