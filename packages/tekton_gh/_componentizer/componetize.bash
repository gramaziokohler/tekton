#!/bin/bash
# Get the absolute path of this script's directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "--- GHUser Componentizer (Mac Fix) ---"

# Rhino internal path to the CLI engine
RHINO_RESOURCES="/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/Current/Resources"
DOTNET="$RHINO_RESOURCES/dotnet/$(uname -m)/dotnet"
RHINO_CODE_DLL="$RHINO_RESOURCES/RhinoCode.dll"

# Check if Rhino 8 is installed
if [ ! -f "$DOTNET" ]; then
    echo "Error: Rhino 8 dotnet engine not found at $DOTNET"
    exit 1
fi

# If this produces nothing - exit 0, no new lines in componentizer.log, no
# fresh .ghuser - the RhinoCode CLI is not executing scripts at all. Seen on
# 2026-10-09 after a Rhino restart: `rhinocode list` showed the instance,
# `script` returned 0 for every target including a three-line probe, and
# -v printed nothing. Rhino itself was fine.
#
# The way through is the LAMCP bridge, which Rhino serves on port 8234 and
# which runs code *inside* the Rhino process (verified: CPython 3.9.10, same
# PID). POST the componentizer to it:
#
#   curl -X POST http://127.0.0.1:8234/exec -H 'Content-Type: application/json' \
#        -d '{"code": "import runpy; runpy.run_path(r\"<abs path>/componentize_cpy.py\", run_name=\"__main__\")"}'
#
# Check the result the same way either route: the timestamp and size of
# ghuser_build/*.ghuser. The log appends, so an old success at the tail
# proves nothing.
echo "Staring componentizer engine... (this might take a few seconds and run silently)"

# Run the python script using Rhino's internal Python 3 engine
"$DOTNET" "$RHINO_CODE_DLL" script "$DIR/componentize_cpy.py"

echo "Done. Check the 'ghuser_build' folder and 'componentizer.log'."
