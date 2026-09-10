#!/bin/bash
# Copy the built .ghuser components into Grasshopper.
#
# The UserObjects do not live under .../8.0/Grasshopper/, as you might expect,
# but under .../8.0/Plug-ins/Grasshopper (b45a29b1-...)/UserObjects.
# The "tekton" subfolder keeps them separate from the other components.
#
# Grasshopper reads UserObjects only at startup - restart Rhino after copying.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$DIR/ghuser_build"

GH_PLUGIN="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper (b45a29b1-4343-4035-989e-044e8580d9cf)"
TARGET="$GH_PLUGIN/UserObjects/tekton"

if [ ! -d "$SOURCE" ]; then
    echo "Nothing built: $SOURCE is missing."
    echo "Run 'python3 _componentizer/build_metadata.py' first, then the componentizer."
    exit 1
fi

count=$(find "$SOURCE" -name '*.ghuser' | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
    echo "No .ghuser files in $SOURCE."
    exit 1
fi

if [ ! -d "$GH_PLUGIN" ]; then
    echo "Grasshopper plugin folder not found:"
    echo "  $GH_PLUGIN"
    echo "Is Rhino 8 installed here?"
    exit 1
fi

mkdir -p "$TARGET"
cp "$SOURCE"/*.ghuser "$TARGET/"

echo "$count components installed to:"
echo "  $TARGET"
echo
echo "Restart Rhino - Grasshopper reads UserObjects only at startup."
