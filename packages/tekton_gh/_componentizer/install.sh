#!/bin/bash
# Gebaute .ghuser-Komponenten nach Grasshopper kopieren.
#
# Die UserObjects liegen nicht unter .../8.0/Grasshopper/, wie man vermuten
# wuerde, sondern unter .../8.0/Plug-ins/Grasshopper (b45a29b1-...)/UserObjects.
# Der Unterordner "tekton" haelt sie von den uebrigen Komponenten getrennt.
#
# Grasshopper liest UserObjects nur beim Start — nach dem Kopieren Rhino neu
# starten.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$DIR/ghuser_build"

GH_PLUGIN="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper (b45a29b1-4343-4035-989e-044e8580d9cf)"
TARGET="$GH_PLUGIN/UserObjects/tekton"

if [ ! -d "$SOURCE" ]; then
    echo "Nichts gebaut: $SOURCE fehlt."
    echo "Erst 'python3 _componentizer/build_metadata.py', dann den Componentizer laufen lassen."
    exit 1
fi

count=$(find "$SOURCE" -name '*.ghuser' | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
    echo "Keine .ghuser in $SOURCE."
    exit 1
fi

if [ ! -d "$GH_PLUGIN" ]; then
    echo "Grasshopper-Plugin-Ordner nicht gefunden:"
    echo "  $GH_PLUGIN"
    echo "Laeuft hier Rhino 8?"
    exit 1
fi

mkdir -p "$TARGET"
cp "$SOURCE"/*.ghuser "$TARGET/"

echo "$count Komponenten installiert nach:"
echo "  $TARGET"
echo
echo "Rhino neu starten — Grasshopper liest UserObjects nur beim Start."
