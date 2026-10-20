#!/bin/bash
# Shared bootstrap, sourced by the two .command launchers.
set -e
TEM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$TEM_ROOT"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "This launcher must run on macOS."
  exit 1
fi
TEM_PYTHON="${TEM_PYTHON:-python3}"
if ! command -v "$TEM_PYTHON" >/dev/null 2>&1; then
  echo "Install Python 3 with Tk support, then run this command again."
  echo "Python downloads: https://www.python.org/downloads/macos/"
  read -r -p "Press Return to close... " _tem_reply
  exit 1
fi
if ! "$TEM_PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
  echo "This Python does not include Tkinter. Use a Python installation with Tk support."
  echo "You can set TEM_PYTHON to the full path of that interpreter."
  read -r -p "Press Return to close... " _tem_reply
  exit 1
fi
if [ ! -x "$TEM_ROOT/.venv/bin/python" ]; then
  "$TEM_PYTHON" -m venv "$TEM_ROOT/.venv"
fi
TEM_RUNNER="$TEM_ROOT/.venv/bin/python"
if ! cmp -s requirements.txt .venv/.tem-requirements; then
  "$TEM_RUNNER" -m pip install -r requirements.txt
  cp requirements.txt .venv/.tem-requirements
fi
