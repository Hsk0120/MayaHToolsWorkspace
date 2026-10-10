#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_NAME="${1:-}"
shift || true

if [[ ! "$LAUNCHER_NAME" =~ ^maya_([0-9]+)_(en|ja)$ ]]; then
    echo "Usage: maya_<version>_<language>.command [Maya arguments]" >&2
    exit 2
fi

MAYA_VERSION="${BASH_REMATCH[1]}"
MAYA_LANGUAGE="${BASH_REMATCH[2]}"

case "$MAYA_LANGUAGE" in
    en) MAYA_UI_LANGUAGE="en_US" ;;
    ja) MAYA_UI_LANGUAGE="ja_JP" ;;
esac
export MAYA_UI_LANGUAGE

export MAYA_DISABLE_CIP="1"
export MAYA_FORCE_PANEL_FOCUS="0"
export MAYA_SHOW_OUTPUT_WINDOW="1"
export MAYA_SCRIPT_PATH="$SCRIPT_DIR/inhouse/mel:$SCRIPT_DIR/package/mel${MAYA_SCRIPT_PATH:+:$MAYA_SCRIPT_PATH}"
export PYTHONPATH="$SCRIPT_DIR/inhouse:$SCRIPT_DIR/inhouse/HTools${PYTHONPATH:+:$PYTHONPATH}"

# pip packages: requirements/<name>.txt is installed into site-packages/<version>/<name>
# and only modules/pip_<name>.mod puts it on PYTHONPATH (keep the .mod in
# modules_disabled to leave it out). Enabled groups that are not installed yet or
# whose requirements changed are installed here before Maya starts.
pip_needed=()
for mod in "$SCRIPT_DIR"/modules/pip_*.mod; do
    [[ -e "$mod" ]] || continue
    name="$(basename "$mod" .mod)"
    name="${name#pip_}"
    requirements="$SCRIPT_DIR/requirements/$name.txt"
    target="$SCRIPT_DIR/site-packages/$MAYA_VERSION/$name"
    if [[ ! -f "$requirements" ]]; then
        echo "[WARN] modules/pip_$name.mod has no requirements/$name.txt." >&2
    elif cmp -s "$requirements" "$target/.installed-requirements.txt"; then
        :
    elif cmp -s "$requirements" "$target.failed"; then
        echo "[WARN] pip package group \"$name\" could not be installed for Maya $MAYA_VERSION. Run install_packages.command $MAYA_VERSION $name to retry." >&2
    else
        pip_needed+=("$name")
    fi
done
if [[ ${#pip_needed[@]} -gt 0 ]]; then
    echo "Installing pip packages for Maya $MAYA_VERSION: ${pip_needed[*]}"
    "$SCRIPT_DIR/install_packages.command" "$MAYA_VERSION" "${pip_needed[@]}"         || echo "[WARN] Some pip packages could not be installed. Maya starts with the previous ones; tools that need them may fail." >&2
fi
export MAYA_PLUG_IN_PATH="$SCRIPT_DIR/inhouse/plugin${MAYA_PLUG_IN_PATH:+:$MAYA_PLUG_IN_PATH}"
export MAYA_MODULE_PATH="$SCRIPT_DIR/modules${MAYA_MODULE_PATH:+:$MAYA_MODULE_PATH}"

MAYA_EXE="${MAYA_EXE:-/Applications/Autodesk/maya${MAYA_VERSION}/Maya.app/Contents/bin/maya}"
if [[ ! -x "$MAYA_EXE" ]]; then
    echo "Maya executable not found: $MAYA_EXE" >&2
    echo "Set MAYA_EXE to the installed Maya executable path." >&2
    exit 1
fi

exec "$MAYA_EXE" "$@"
