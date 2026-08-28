"""Componentizer aus einer *laufenden* Rhino-Instanz heraus starten.

Warum nicht einfach `componetize.bash`: dessen Weg über die RhinoCode-CLI
(`rhinocode script ...`) war am 2026-08-28 auf diesem Rechner wirkungslos —
Exit-Code 0, aber das Skript lief nachweislich nicht (kein Log, keine Ausgabe,
kein Seiteneffekt). Das betrifft auch den unveränderten Componentizer in
`lorin-gh-tools`, liegt also nicht an Tekton.

Der Componentizer braucht `clr`/`System`, also einen .NET-Prozess. Eine
laufende Rhino-Instanz ist einer. Dieses Skript im Rhino-Python-Editor öffnen
und ausführen (oder über eine Skript-Komponente), dann baut es alle Bundles
aus ``components/`` nach ``_componentizer/ghuser_build/``.

Sollte die CLI wieder funktionieren, ist ``bash componetize.bash`` weiterhin
der bequemere Weg — beide erzeugen dasselbe.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "componentize_cpy.py")


def main():
    if not os.path.isfile(SCRIPT):
        raise RuntimeError("componentize_cpy.py nicht gefunden neben {}".format(HERE))

    # Der Componentizer parst sys.argv und laeuft nur unter __main__.
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
    print("\n{} Komponenten in {}".format(len(built), build_dir))
    print(
        "\nZum Installieren nach:\n"
        "  ~/Library/Application Support/McNeel/Rhinoceros/8.0/Grasshopper/UserObjects/\n"
        "kopieren und Rhino neu starten."
    )
    return built


if __name__ == "__main__":
    main()
