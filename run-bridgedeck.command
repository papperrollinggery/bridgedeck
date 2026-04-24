#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
(sleep 1; open "http://127.0.0.1:8899") &
exec /usr/bin/env python3 "$SCRIPT_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899
