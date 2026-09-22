#!/bin/bash
exec "$(dirname "$0")/maya_core.command" "$(basename "$0" .command)" "$@"
