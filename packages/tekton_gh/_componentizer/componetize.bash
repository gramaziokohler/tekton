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

echo "Staring componentizer engine... (this might take a few seconds and run silently)"

# Run the python script using Rhino's internal Python 3 engine
"$DOTNET" "$RHINO_CODE_DLL" script "$DIR/componentize_cpy.py"

echo "Done. Check the 'ghuser_build' folder and 'componentizer.log'."
