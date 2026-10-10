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
# pip packages in site-packages/<version> (only these launchers use them).
# Installed here, before PYTHONPATH is built, when they are missing or
# requirements.txt has changed since the last install.
SITE_DIR="$SCRIPT_DIR/site-packages/$MAYA_VERSION"
if grep -qvE '^[[:space:]]*(#|$)' "$SCRIPT_DIR/requirements.txt" 2>/dev/null         && ! cmp -s "$SCRIPT_DIR/requirements.txt" "$SITE_DIR/.installed-requirements.txt"; then
    echo "Installing pip packages for Maya $MAYA_VERSION: requirements.txt is new or changed."
    "$SCRIPT_DIR/install_packages.command" "$MAYA_VERSION"         || echo "[WARN] Could not install pip packages. Maya starts with the previous packages; tools that need new ones may fail." >&2
fi
SITE_ENTRY=""
[[ -d "$SITE_DIR" ]] && SITE_ENTRY=":$SITE_DIR"
export PYTHONPATH="$SCRIPT_DIR/inhouse:$SCRIPT_DIR/inhouse/HTools$SITE_ENTRY${PYTHONPATH:+:$PYTHONPATH}"
export MAYA_PLUG_IN_PATH="$SCRIPT_DIR/inhouse/plugin${MAYA_PLUG_IN_PATH:+:$MAYA_PLUG_IN_PATH}"
export MAYA_MODULE_PATH="$SCRIPT_DIR/modules${MAYA_MODULE_PATH:+:$MAYA_MODULE_PATH}"

MAYA_EXE="${MAYA_EXE:-/Applications/Autodesk/maya${MAYA_VERSION}/Maya.app/Contents/bin/maya}"
if [[ ! -x "$MAYA_EXE" ]]; then
    echo "Maya executable not found: $MAYA_EXE" >&2
    echo "Set MAYA_EXE to the installed Maya executable path." >&2
    exit 1
fi

exec "$MAYA_EXE" "$@"
