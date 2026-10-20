#!/bin/bash
set -e
cd "$(dirname "$0")"
source ./mac-common.sh
"$TEM_RUNNER" -m pip install pyinstaller dmgbuild==1.6.7
"$TEM_RUNNER" "$TEM_ROOT/build_app.py"
echo "Built and checked: $TEM_ROOT/dist/TEM-Studio.app"
echo "This is a local, unsigned build. Build separately on Intel and Apple Silicon."
read -r -p "Press Return to close... " _tem_reply
