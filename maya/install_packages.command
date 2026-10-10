#!/bin/bash
# Install pip package groups (requirements/<name>.txt) into
# site-packages/<Maya version>/<name>, using the mayapy of each version.
# modules/pip_<name>.mod puts a group on PYTHONPATH; a disabled .mod is
# created in modules_disabled for a group that has none.
#
#   install_packages.command                    all groups, all installed Maya versions
#   install_packages.command 2026 2027          all groups, given versions
#   install_packages.command 2026 scipy libigl  given groups, given versions
#
# Numbers are Maya versions, other words are group names.
# MAYA_INSTALL_ROOT overrides /Applications/Autodesk.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="${MAYA_INSTALL_ROOT:-/Applications/Autodesk}"
HELPER="$SCRIPT_DIR/../tools/install_maya_packages.py"

versions=()
groups=()
for arg in "$@"; do
    if [[ "$arg" =~ ^[0-9]+$ ]]; then versions+=("$arg"); else groups+=("$arg"); fi
done
[[ ${#versions[@]} -eq 0 ]] && versions=(2022 2023 2024 2025 2026 2027)

found=0
failed=""
for version in "${versions[@]}"; do
    mayapy="$INSTALL_ROOT/maya$version/Maya.app/Contents/bin/mayapy"
    if [[ -x "$mayapy" ]]; then
        found=1
        echo
        echo "==== Maya $version ===="
        "$mayapy" "$HELPER" --requirements-dir "$SCRIPT_DIR/requirements" \
            --target-root "$SCRIPT_DIR/site-packages/$version" \
            --modules-dir "$SCRIPT_DIR/modules" --disabled-modules-dir "$SCRIPT_DIR/modules_disabled" \
            --groups ${groups[@]+"${groups[@]}"} || failed="$failed $version"
    else
        echo "[SKIP] Maya $version is not installed: $mayapy"
    fi
done

echo
if [[ $found -eq 0 ]]; then
    echo "[ERROR] No Maya was found under \"$INSTALL_ROOT\"." >&2
    exit 1
elif [[ -n "$failed" ]]; then
    echo "[ERROR] Some groups failed for Maya:$failed" >&2
    exit 1
fi
echo "Done."
