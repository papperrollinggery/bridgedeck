#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if /usr/bin/curl -fsS -H "X-CCSBT-Token: probe" "http://127.0.0.1:8899/" >/dev/null 2>&1; then
  open "http://127.0.0.1:8899"
  exit 0
fi
(sleep 1; open "http://127.0.0.1:8899") &
exec /usr/bin/env python3 "$SCRIPT_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899
