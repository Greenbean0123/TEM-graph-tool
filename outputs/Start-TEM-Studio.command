#!/bin/bash
set -e
cd "$(dirname "$0")"
source ./mac-common.sh
exec "$TEM_RUNNER" "$TEM_ROOT/startup_launcher.py"
