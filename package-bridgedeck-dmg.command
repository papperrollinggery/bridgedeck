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

log_event() {
  /bin/echo "$(/bin/date '+%Y-%m-%d %H:%M:%S') launcher: $*" >> "$LOG_FILE"
}

ui_running() {
  /usr/bin/curl -fsS -H "X-CCSBT-Token: probe" "$APP_URL/" >/dev/null 2>&1
}

open_ui() {
  log_event "open_ui $APP_URL"
  open "$APP_URL"
}

start_ui() {
  log_event "start_ui"
  /usr/bin/nohup /usr/bin/python3 "$RESOURCE_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899 >> "$LOG_FILE" 2>&1 &
  for _ in {1..20}; do
    if ui_running; then
      open_ui
      return 0
    fi
    sleep 0.2
  done
  open_ui
}

stop_ui_keep_bridge() {
  log_event "stop_ui_keep_bridge"
  for pid in $(/usr/sbin/lsof -tiTCP:8899 -sTCP:LISTEN 2>/dev/null); do
    cmd="$(/bin/ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"bridgedeck.py"* ]]; then
      /bin/kill "$pid" 2>/dev/null || true
    fi
  done
  /usr/bin/osascript -e 'display notification "8876 Local Bridge 继续运行" with title "BridgeDeck UI 已关闭"' >/dev/null 2>&1 || true
}

start_bridge_only() {
  log_event "start_bridge_only"
  CODEX_BRIDGE_SCRIPT="$RESOURCE_DIR/local_codex_bridge.py" /usr/bin/python3 "$RESOURCE_DIR/bridgedeck.py" --local-bridge start >> "$LOG_FILE" 2>&1 &
  /usr/bin/osascript -e 'display notification "8876 Local Bridge 已启动或已在运行" with title "BridgeDeck"' >/dev/null 2>&1 || true
}

if ui_running; then
  log_event "launcher_start ui_running=1"
  choice="$(/usr/bin/osascript <<'APPLESCRIPT' 2>/dev/null || true
button returned of (display dialog "BridgeDeck UI (8899) 已在运行。" buttons {"取消", "关闭 UI 保留 Bridge", "打开 UI"} default button "打开 UI" cancel button "取消" with title "BridgeDeck")
APPLESCRIPT
)"
  log_event "dialog_choice=${choice:-<empty>}"
  case "$choice" in
    "打开 UI") open_ui ;;
    "关闭 UI 保留 Bridge") stop_ui_keep_bridge ;;
    "") log_event "dialog_empty_fallback=open_ui"; open_ui ;;
    *) exit 0 ;;
  esac
else
  log_event "launcher_start ui_running=0"
  choice="$(/usr/bin/osascript <<'APPLESCRIPT' 2>/dev/null || true
button returned of (display dialog "BridgeDeck UI 未运行。要打开配置页，还是只启动 8876 Local Bridge？" buttons {"取消", "只启动 Bridge", "打开 UI"} default button "打开 UI" cancel button "取消" with title "BridgeDeck")
APPLESCRIPT
)"
  log_event "dialog_choice=${choice:-<empty>}"
  case "$choice" in
    "打开 UI") start_ui ;;
    "只启动 Bridge") start_bridge_only ;;
    "") log_event "dialog_empty_fallback=start_ui"; start_ui ;;
    *) exit 0 ;;
  esac
fi
LAUNCHER
if command -v swiftc >/dev/null 2>&1; then
  TMP_LAUNCHER="$(mktemp /tmp/bridgedeck-launcher.XXXXXX)"
  swiftc "$ROOT/BridgeDeckLauncher.swift" -o "$TMP_LAUNCHER"
  cp "$TMP_LAUNCHER" "$MACOS/launcher"
  rm -f "$TMP_LAUNCHER"
fi
chmod +x "$MACOS/launcher"

/usr/bin/hdiutil create -volname "$APP_NAME" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG"
echo "$DMG"
