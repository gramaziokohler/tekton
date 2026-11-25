#!/usr/bin/env python3
"""Set up Tekton, or say exactly what is missing.

Tekton runs in two Pythons at once - Rhino's 3.9 for the Grasshopper side and
a 3.12 worker for everything that needs gRPC - and the failure modes are all
of the same shape: something is installed, but not the thing the other half
expects. This script checks rather than assumes, and every check names what to
do when it fails.

    python3 install.py              # check, report, change nothing
    python3 install.py --fix        # also install what is missing
    python3 install.py --fix --build   # ... and build/install the components

It is deliberately dependency-free and runs on any Python 3.8+, because the
first thing it has to be able to report is "you have no suitable Python".
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The Rhino venv name every component header names (`# venv: ...`). Rhino
#: silently creates an *empty* env for an unknown name, so this is not
#: cosmetic - a mismatch looks like "compas_timber is missing".
RHINO_VENV_NAME = "tekton-test"

#: Packages the Rhino side needs, beyond what Rhino itself ships.
RHINO_REQUIREMENTS = ("compas_timber",)

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
MARKS = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL ", INFO: "      "}


class Report:
    """Collects findings so the summary can be about all of them at once."""

    def __init__(self):
        self.rows = []

    def add(self, status, what, detail="", fix=""):
        self.rows.append((status, what, detail, fix))
        line = "[{}] {}".format(MARKS[status], what)
        if detail:
            line += " - " + detail
        print(line)
        if fix and status in (WARN, FAIL):
            for piece in fix.splitlines():
                print("         " + piece)
        return status

    @property
    def failures(self):
        return [row for row in self.rows if row[0] == FAIL]

    @property
    def warnings(self):
        return [row for row in self.rows if row[0] == WARN]


#: Variables that make one Python's installation visible to another. An
#: activated venv (or uv's own interpreter) exports PYTHONHOME, and Rhino's
#: 3.9 then starts against a 3.12 standard library and dies with "can't
#: initialize sys standard streams" - which this script used to report as
#: "compas_timber missing or too old". Every child here is either a different
#: interpreter or a venv that finds its own home through pyvenv.cfg, so none
#: of them wants these inherited.
LEAKING_VARS = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE")


def run(command, **kwargs):
    """Run a command, returning (code, stdout+stderr). Never raises."""
    environment = kwargs.pop("env", None) or os.environ
    environment = dict((k, v) for k, v in environment.items() if k not in LEAKING_VARS)
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True, env=environment,
            timeout=kwargs.pop("timeout", 900), **kwargs)
        return finished.returncode, (finished.stdout or "") + (finished.stderr or "")
    except FileNotFoundError:
        return 127, "not found: {}".format(command[0])
    except subprocess.TimeoutExpired:
        return 124, "timed out"


# --------------------------------------------------------------- the checks

def check_uv(report, fix):
    """uv drives the worker environment; without it nothing else works."""
    if shutil.which("uv"):
        code, out = run(["uv", "--version"])
        return report.add(OK, "uv", out.strip())
    return report.add(
        FAIL, "uv", "not on PATH",
        "Install it: curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "or: brew install uv")


def check_pins(report, fix):
    """pyproject.toml and requirements.txt must name the same compas_timber.

    They are read by different installers - uv for the worker, pip for the
    Rhino venv - so a drift here gives you two different compas_timber
    versions and an import error that names neither file. This has happened.
    """
    pins = {}
    for name in ("pyproject.toml", "requirements.txt"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path) as handle:
            text = handle.read()
        # The two files spell the same pin differently: pyproject uses uv's
        # `rev = "..."`, requirements.txt pip's `git@...`. Both forms count.
        found = (re.findall(r"compas_timber\.git@([0-9a-f]{7,40})", text)
                 or re.findall(r"compas_timber\.git\"?,?\s*rev\s*=\s*\"([0-9a-f]{7,40})", text))
        if found:
            pins[name] = found[0]

    if len(pins) < 2:
        return report.add(WARN, "compas_timber pin", "could not read both files")
    if len(set(pins.values())) == 1:
        return report.add(OK, "compas_timber pin", list(pins.values())[0][:12] + " in both files")
    return report.add(
        FAIL, "compas_timber pin",
        "; ".join("{}={}".format(k, v[:12]) for k, v in pins.items()),
        "The worker and the Rhino venv would get different versions.\n"
        "Make both files name the same revision, then re-run with --fix.")


def worker_python():
    """The interpreter inside the repo's .venv, whether or not it exists yet."""
    if platform.system() == "Windows":
        return os.path.join(HERE, ".venv", "Scripts", "python.exe")
    return os.path.join(HERE, ".venv", "bin", "python")


def check_worker_env(report, fix):
    """The 3.12 environment the worker runs in."""
    python = worker_python()

    if not os.path.exists(python):
        if not fix:
            return report.add(FAIL, "worker venv", "missing", "Run with --fix, or: uv sync --extra dev")
        print("       creating the worker venv (uv sync --extra dev) ...")
        code, out = run(["uv", "sync", "--extra", "dev"], cwd=HERE)
        if code != 0:
            return report.add(FAIL, "worker venv", "uv sync failed", out.strip()[-400:])
        report.add(OK, "worker venv", "created")

    code, out = run([python, "--version"])
    if code != 0:
        return report.add(FAIL, "worker venv", "python not runnable")
    version = out.strip()

    missing = []
    for module in ("compas", "compas_timber", "tekton_core", "tekton_opensees", "gmsh"):
        code, _ = run([python, "-c", "import {}".format(module)])
        if code != 0:
            missing.append(module)

    if missing:
        if fix:
            print("       installing the workspace (uv sync --extra dev) ...")
            code, out = run(["uv", "sync", "--extra", "dev"], cwd=HERE)
            if code != 0:
                return report.add(FAIL, "worker packages", "uv sync failed", out.strip()[-400:])
            missing = [m for m in missing
                       if run([python, "-c", "import {}".format(m)])[0] != 0]
        if missing:
            return report.add(FAIL, "worker packages", "missing: " + ", ".join(missing),
                              "uv sync --extra dev")
    return report.add(OK, "worker venv", "{}, all packages importable".format(version))


def check_plate_solver(report, fix):
    """compas_timber.structural must carry the plate solver.

    The released COMPAS Timber does not; only the pinned branch revision does.
    This is the check that catches "PlateStructuralElementSolver cannot be
    imported" before it happens in Rhino.
    """
    python = worker_python()
    if not os.path.exists(python):
        return report.add(INFO, "plate solver", "skipped, no worker venv yet")
    code, out = run([python, "-c",
                     "from compas_timber.structural import PlateStructuralElementSolver; print('ok')"])
    if code == 0:
        return report.add(OK, "plate solver", "compas_timber.structural complete")
    return report.add(
        FAIL, "plate solver", "PlateStructuralElementSolver not importable",
        "The pinned compas_timber revision is too old, or the released one got installed.\n"
        "Check the pin in pyproject.toml, then: uv sync --extra dev --reinstall-package compas_timber")


def find_rhino_python():
    """Rhino's own CPython 3.9, or None."""
    candidates = []
    if platform.system() == "Darwin":
        candidates.append(os.path.expanduser("~/.rhinocode/py39-rh8/python3.9"))
    elif platform.system() == "Windows":
        candidates.append(os.path.expandvars(r"%USERPROFILE%\.rhinocode\py39-rh8\python.exe"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def find_rhino_venv(name=RHINO_VENV_NAME):
    """The site-env Rhino made for this venv name, or None.

    Rhino appends a hash to the name, so the directory is `tekton-test-XXXX`.
    """
    base = os.path.expanduser("~/.rhinocode/py39-rh8/site-envs")
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        if entry == name or entry.startswith(name + "-"):
            return os.path.join(base, entry)
    return None


def check_rhino(report, fix):
    """Rhino's Python, the named venv, and compas_timber inside it."""
    python = find_rhino_python()
    if python is None:
        return report.add(
            WARN, "Rhino Python", "not found",
            "Only needed for the Grasshopper components.\n"
            "Install Rhino 8 and open it once, so it creates ~/.rhinocode.")
    code, out = run([python, "--version"])
    report.add(OK, "Rhino Python", out.strip())

    venv = find_rhino_venv()
    if venv is None:
        return report.add(
            WARN, "Rhino venv '{}'".format(RHINO_VENV_NAME), "not created yet",
            "Rhino creates it the first time a component with\n"
            "'# venv: {}' in its header runs. Drop Tekton Info on the\n"
            "canvas once, then re-run this script with --fix.".format(RHINO_VENV_NAME))

    code, out = run([python, "-c",
                     "import sys; sys.path.insert(0, {!r});"
                     "from compas_timber.structural import PlateStructuralElementSolver;"
                     "import compas_timber; print(compas_timber.__version__)".format(venv)])
    if code == 0:
        return report.add(OK, "Rhino venv", "compas_timber {} with the plate solver".format(out.strip()))

    if not fix:
        return report.add(
            FAIL, "Rhino venv", "compas_timber missing or too old",
            "Re-run with --fix to install the pinned revision into it.")

    pin = None
    with open(os.path.join(HERE, "requirements.txt")) as handle:
        found = re.findall(r"(compas_timber @ git\+\S+)", handle.read())
        if found:
            pin = found[0].split("@ ", 1)[1]
    if not pin:
        return report.add(FAIL, "Rhino venv", "no compas_timber pin in requirements.txt")

    print("       installing compas_timber into the Rhino venv ...")
    code, out = run([python, "-m", "pip", "install", "--target", venv,
                     "--upgrade", "--no-deps", pin])
    if code != 0:
        return report.add(FAIL, "Rhino venv", "pip install failed", out.strip()[-400:])
    code, out = run([python, "-c",
                     "import sys; sys.path.insert(0, {!r});"
                     "from compas_timber.structural import PlateStructuralElementSolver;"
                     "import compas_timber; print(compas_timber.__version__)".format(venv)])
    if code != 0:
        return report.add(FAIL, "Rhino venv", "still not importable after install", out.strip()[-300:])
    return report.add(OK, "Rhino venv", "compas_timber {} installed".format(out.strip()))


def check_repo_path(report, fix):
    """The components need to find the repo; several ways do that."""
    cache = os.path.expanduser("~/.tekton/repo-root")
    if os.environ.get("TEKTON_REPO"):
        return report.add(OK, "repo discovery", "TEKTON_REPO is set")
    if os.path.exists(cache):
        with open(cache) as handle:
            remembered = handle.read().strip()
        if os.path.isdir(os.path.join(remembered, "packages")):
            return report.add(OK, "repo discovery", "remembered: " + remembered)
    if fix:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w") as handle:
                handle.write(HERE)
            return report.add(OK, "repo discovery", "remembered this checkout")
        except OSError as error:
            return report.add(WARN, "repo discovery", str(error))
    return report.add(
        INFO, "repo discovery", "components will find it themselves",
        "A component with a 'repo' input remembers the path on first use.\n"
        "--fix writes it now, so even the first solve finds it.")


def check_api_key(report, fix):
    """Only needed for RFEM/RSTAB."""
    env = os.path.join(HERE, ".env")
    if os.environ.get("TEKTON_API_KEY") or os.environ.get("DLUBAL_API_KEY"):
        return report.add(OK, "Dlubal API key", "from the environment")
    if os.path.exists(env):
        with open(env) as handle:
            if re.search(r"DLUBAL_API_KEY\s*=\s*\S", handle.read()):
                return report.add(OK, "Dlubal API key", ".env")
    return report.add(
        INFO, "Dlubal API key", "not set - only needed for rfem/rstab",
        "cp .env.example .env, then put the key in it. .env is gitignored.")


def user_objects_dir():
    """Where Grasshopper reads .ghuser files from on this platform.

    On macOS they sit inside the Grasshopper plug-in folder, whose name
    carries the plug-in GUID; on Windows they are simply under %APPDATA%.
    """
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "Grasshopper", "UserObjects", "tekton")
    return os.path.expanduser(
        "~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/"
        "Grasshopper (b45a29b1-4343-4035-989e-044e8580d9cf)/UserObjects/tekton")


def _install_built(report, target, built):
    """Copy the freshly built bundles over the installed ones."""
    if not os.path.isdir(built):
        return report.add(FAIL, "components", "nothing was built", built)
    if not os.path.isdir(target):
        os.makedirs(target)
    for name in os.listdir(target):
        if name.endswith(".ghuser"):
            os.remove(os.path.join(target, name))
    copied = 0
    for name in sorted(os.listdir(built)):
        if name.endswith(".ghuser"):
            shutil.copy2(os.path.join(built, name), os.path.join(target, name))
            copied += 1
    return report.add(OK, "components", "{} built and installed".format(copied),
                      "Restart Rhino - Grasshopper reads UserObjects at startup.")


def _build_windows(report, componentizer):
    """Build the .ghuser files with pythonnet; no Rhino needed.

    The .NET step only has to load GH_IO.dll, which pythonnet can do on the
    .NET Framework. Rhino's own RhinoCode refuses to run without a live
    Rhino, so on Windows this is the shorter path, not a workaround.
    """
    python = worker_python()
    code, _ = run([python, "-c", "import clr"])
    if code != 0:
        print("       installing pythonnet into the worker venv ...")
        code, out = run(["uv", "pip", "install", "pythonnet"], cwd=HERE)
        if code != 0:
            return report.add(FAIL, "components", "pythonnet could not be installed", out.strip()[-300:])
    print("       building the components (pythonnet) ...")
    code, out = run([python, os.path.join(componentizer, "componentize_cpy.py")], cwd=componentizer)
    if code != 0:
        return report.add(FAIL, "components", "componentizer failed", out.strip()[-400:])
    return None


def _build_macos(report, componentizer):
    """Build by driving a running Rhino, which is the only way on macOS."""
    resources = "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/Current/Resources"
    dotnet = os.path.join(resources, "dotnet", platform.machine(), "dotnet")
    rhinocode = os.path.join(resources, "RhinoCode.dll")
    if not os.path.exists(dotnet):
        return report.add(FAIL, "components", "Rhino's dotnet not found",
                          "Is Rhino 8 installed in /Applications?")
    code, out = run([dotnet, rhinocode, "list"])
    instance = None
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            instance = parts[1]
            break
    if instance is None:
        return report.add(
            FAIL, "components", "no running Rhino",
            "The componentizer drives a live Rhino. Start Rhino 8 and re-run.")
    print("       building the components (via Rhino) ...")
    run([dotnet, rhinocode, "-r", instance, "script",
         os.path.join(componentizer, "componentize_cpy.py")])
    return None


def check_components(report, fix, build):
    """The .ghuser files Grasshopper reads."""
    bundles = os.path.join(HERE, "packages", "tekton_gh", "components")
    count = len([d for d in os.listdir(bundles)
                 if os.path.isdir(os.path.join(bundles, d))]) if os.path.isdir(bundles) else 0

    target = user_objects_dir()
    installed = len([f for f in os.listdir(target) if f.endswith(".ghuser")]) \
        if os.path.isdir(target) else 0

    if installed == count and count:
        return report.add(OK, "components", "{} installed".format(installed))

    detail = "{} bundles, {} installed".format(count, installed)
    if not build:
        hint = "Re-run with --build."
        if platform.system() != "Windows":
            hint += "\nRhino must be running (the componentizer drives it)."
        return report.add(WARN if installed else INFO, "components", detail, hint)

    componentizer = os.path.join(HERE, "packages", "tekton_gh", "_componentizer")
    code, out = run([worker_python(), os.path.join(componentizer, "build_metadata.py")],
                    cwd=os.path.dirname(componentizer))
    if code != 0:
        return report.add(FAIL, "components", "build_metadata failed", out.strip()[-300:])

    builder = _build_windows if platform.system() == "Windows" else _build_macos
    failed = builder(report, componentizer)
    if failed is not None:
        return failed
    return _install_built(report, target, os.path.join(componentizer, "ghuser_build"))


def check_tests(report, fix):
    """A green suite is the cheapest proof the install actually works."""
    python = worker_python()
    if not os.path.exists(python):
        return report.add(INFO, "tests", "skipped, no worker venv")
    code, out = run([python, "-m", "pytest", "tests/unit", "-q", "--no-header"], cwd=HERE)
    last = [line for line in out.strip().splitlines() if line.strip()][-1] if out.strip() else ""
    if code == 0:
        return report.add(OK, "tests", last[:70])
    return report.add(FAIL, "tests", last[:70], "Something is off with the install; the output above says what.")


# ---------------------------------------------------------------- the entry

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fix", action="store_true",
                        help="install what is missing, instead of only reporting it")
    parser.add_argument("--build", action="store_true",
                        help="also build and install the Grasshopper components (needs a running Rhino)")
    parser.add_argument("--skip-tests", action="store_true", help="do not run the test suite")
    args = parser.parse_args()

    print("Tekton setup check" + (" (--fix)" if args.fix else " (read-only; use --fix to install)"))
    print("Repository: {}".format(HERE))
    print("Platform:   {} {}".format(platform.system(), platform.machine()))
    print()

    report = Report()
    check_uv(report, args.fix)
    check_pins(report, args.fix)
    check_worker_env(report, args.fix)
    check_plate_solver(report, args.fix)
    check_rhino(report, args.fix)
    check_repo_path(report, args.fix)
    check_api_key(report, args.fix)
    check_components(report, args.fix, args.build)
    if not args.skip_tests:
        check_tests(report, args.fix)

    print()
    if report.failures:
        print("{} check(s) failed - see the lines marked FAIL above.".format(len(report.failures)))
        if not args.fix:
            print("Several of them are fixable: re-run with --fix.")
        return 1
    if report.warnings:
        print("Usable. {} warning(s) - the Grasshopper side may be incomplete.".format(
            len(report.warnings)))
        return 0
    print("Everything checks out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
