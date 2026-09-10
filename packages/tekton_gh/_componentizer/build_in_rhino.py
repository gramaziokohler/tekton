"""Run the componentizer from inside a *running* Rhino instance.

Why not just `componetize.bash`: its route through the RhinoCode CLI
(`rhinocode script ...`) had no effect on this machine on 2026-08-28 -
exit code 0, but the script demonstrably did not run (no log, no output, no
side effect). This also affects the unmodified componentizer in
`lorin-gh-tools`, so it is not Tekton's fault.

The componentizer needs `clr`/`System`, so a .NET process. A running Rhino
instance is one. Open this script in the Rhino Python editor and run it (or
run it from a script component), and it builds all bundles from ``components/``
into ``_componentizer/ghuser_build/``.

If the CLI works again, ``bash componetize.bash`` is still the more convenient
route - both produce the same thing.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "componentize_cpy.py")


def main():
    if not os.path.isfile(SCRIPT):
        raise RuntimeError("componentize_cpy.py not found next to {}".format(HERE))

    # The componentizer parses sys.argv and only runs under __main__.
    old_argv = sys.argv
    sys.argv = [SCRIPT]
    try:
        with open(SCRIPT) as handle:
            source = handle.read()
        namespace = {"__name__": "__main__", "__file__": SCRIPT}
        exec(compile(source, SCRIPT, "exec"), namespace)
    finally:
        sys.argv = old_argv

    build_dir = os.path.join(HERE, "ghuser_build")
    built = sorted(f for f in os.listdir(build_dir) if f.endswith(".ghuser"))
    print("\n{} components in {}".format(len(built), build_dir))
    print(
        "\nTo install, copy them to:\n"
        "  ~/Library/Application Support/McNeel/Rhinoceros/8.0/Grasshopper/UserObjects/\n"
        "and restart Rhino."
    )
    return built


if __name__ == "__main__":
    main()
