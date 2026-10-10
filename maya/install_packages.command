#!/bin/bash
# Install pip packages listed in requirements.txt into site-packages/<Maya version>,
# using the mayapy of each version. Only maya_core.command adds that folder to PYTHONPATH.
#
#   install_packages.command            all installed Maya versions
#   install_packages.command 2026 2027  only the given versions
#
# MAYA_INSTALL_ROOT overrides /Applications/Autodesk.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="${MAYA_INSTALL_ROOT:-/Applications/Autodesk}"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
HELPER="$SCRIPT_DIR/../tools/install_maya_packages.py"

if [[ $# -eq 0 ]]; then
    set -- 2022 2023 2024 2025 2026 2027
fi

found=0
failed=""
for version in "$@"; do
    mayapy="$INSTALL_ROOT/maya$version/Maya.app/Contents/bin/mayapy"
    if [[ -x "$mayapy" ]]; then
        found=1
        echo
        echo "==== Maya $version ===="
        "$mayapy" "$HELPER" --requirements "$REQUIREMENTS" --target "$SCRIPT_DIR/site-packages/$version" \
            || failed="$failed $version"
    else
        echo "[SKIP] Maya $version is not installed: $mayapy"
    fi
done

echo
if [[ $found -eq 0 ]]; then
    echo "[ERROR] No Maya was found under \"$INSTALL_ROOT\"." >&2
    exit 1
elif [[ -n "$failed" ]]; then
    echo "[ERROR] Failed for Maya:$failed" >&2
    exit 1
fi
echo "Done."
