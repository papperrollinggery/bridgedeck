#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BridgeDeck"
BUILD_DIR="$ROOT/dist"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
ICON_FILE="$ROOT/assets/BridgeDeck.icns"
DMG="$BUILD_DIR/BridgeDeck.dmg"
APP_VERSION="$(/usr/bin/env python3 - "$ROOT/bridgedeck.py" <<'PY'
import ast
import sys
from pathlib import Path
tree = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "APP_VERSION":
                print(ast.literal_eval(node.value))
                raise SystemExit
raise SystemExit("APP_VERSION not found")
PY
)"

rm -rf "$APP_DIR" "$DMG"
mkdir -p "$MACOS" "$RESOURCES"

cp "$ROOT/bridgedeck.py" "$RESOURCES/bridgedeck.py"
cp "$ROOT/local_codex_bridge.py" "$RESOURCES/local_codex_bridge.py"
cp "$ROOT/README.md" "$RESOURCES/README.md"
cp "$ROOT/SECURITY.md" "$RESOURCES/SECURITY.md"
cp "$ROOT/CONTRIBUTING.md" "$RESOURCES/CONTRIBUTING.md"
cp "$ROOT/CHANGELOG.md" "$RESOURCES/CHANGELOG.md"
cp "$ROOT/OPEN_SOURCE_CHECKLIST.md" "$RESOURCES/OPEN_SOURCE_CHECKLIST.md"
cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"
cp "$ROOT/COMMERCIAL.md" "$RESOURCES/COMMERCIAL.md"
cp "$ICON_FILE" "$RESOURCES/BridgeDeck.icns"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleIdentifier</key>
  <string>local.bridgedeck.app</string>
  <key>CFBundleName</key>
  <string>BridgeDeck</string>
  <key>CFBundleDisplayName</key>
  <string>BridgeDeck</string>
  <key>CFBundleIconFile</key>
  <string>BridgeDeck.icns</string>
  <key>LSUIElement</key>
  <true/>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
</dict>
</plist>
PLIST

cat > "$MACOS/launcher" <<'LAUNCHER'
#!/bin/zsh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCE_DIR="$SCRIPT_DIR/../Resources"
LOG_DIR="$HOME/Library/Logs"
LOG_FILE="$LOG_DIR/bridgedeck-app.log"
APP_URL="http://127.0.0.1:8899"
mkdir -p "$LOG_DIR"

if [[ "${1:-}" == "--self-test" ]]; then
  echo "BridgeDeckLauncher OK"
  exit 0
fi

log_event() {
  /bin/echo "$(/bin/date '+%Y-%m-%d %H:%M:%S') launcher: $*" >> "$LOG_FILE"
}

python_bin() {
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo /usr/bin/python3
}

ui_running() {
  /usr/bin/curl -fsS -H "X-CCSBT-Token: probe" "$APP_URL/" >/dev/null 2>&1
}

open_ui() {
  log_event "open_ui $APP_URL"
  /usr/bin/open "$APP_URL" >/dev/null 2>&1 &
}

start_ui() {
  log_event "start_ui"
  /usr/bin/nohup "$(python_bin)" "$RESOURCE_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899 >> "$LOG_FILE" 2>&1 &
  for _ in {1..30}; do
    if ui_running; then
      open_ui
      return 0
    fi
    sleep 0.2
  done
  open_ui
}

if ui_running; then
  log_event "launcher_start ui_running=1"
  open_ui
else
  log_event "launcher_start ui_running=0"
  start_ui
fi
LAUNCHER
chmod +x "$MACOS/launcher"

/usr/bin/hdiutil create -volname "$APP_NAME" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG"
echo "$DMG"
