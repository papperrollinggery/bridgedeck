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

run_preflight() {
  echo "BridgeDeck package preflight"
  /usr/bin/env python3 -m py_compile "$ROOT/bridgedeck.py" "$ROOT/local_codex_bridge.py" "$ROOT/model_catalog.py"
  /bin/zsh -n "$ROOT/package-bridgedeck-dmg.command"
  if [[ "${BRIDGEDECK_PACKAGE_TESTS:-0}" == "1" ]]; then
    /usr/bin/env python3 -m unittest discover -s "$ROOT/tests"
  fi
}

run_preflight

rm -rf "$APP_DIR" "$DMG"
mkdir -p "$MACOS" "$RESOURCES"

cp "$ROOT/bridgedeck.py" "$RESOURCES/bridgedeck.py"
cp "$ROOT/local_codex_bridge.py" "$RESOURCES/local_codex_bridge.py"
cp "$ROOT/model_catalog.py" "$RESOURCES/model_catalog.py"
cp "$ROOT/README.md" "$RESOURCES/README.md"
cp "$ROOT/README.zh-CN.md" "$RESOURCES/README.zh-CN.md"
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
INSTALL_STATE="$HOME/Library/Application Support/BridgeDeck/install-state.json"
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
  /usr/bin/curl -fsS -H "X-CCSBT-Token: probe" "$APP_URL/" >/dev/null 2>&1 && return 0
  ui_port_owner_commands | /usr/bin/grep -q "bridgedeck.py"
}

ui_port_owner_commands() {
  local pid cmd
  /usr/sbin/lsof -tiTCP:8899 -sTCP:LISTEN 2>/dev/null | while read -r pid; do
    [[ -n "$pid" ]] || continue
    cmd="$(/bin/ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ -n "$cmd" ]] && /bin/echo "$cmd"
  done
}

open_ui() {
  local open_url="$APP_URL/?t=$(/bin/date +%s)"
  log_event "open_ui $open_url"
  /usr/bin/open "$open_url" >/dev/null 2>&1
}

start_ui() {
  log_event "start_ui"
  if ui_running; then
    open_ui
    return 0
  fi
  /usr/bin/nohup "$(python_bin)" "$RESOURCE_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899 >> "$LOG_FILE" 2>&1 &
  for _ in {1..40}; do
    if ui_running; then
      open_ui
      return 0
    fi
    sleep 0.2
  done
  owners="$(ui_port_owner_commands)"
  if [[ -n "$owners" ]]; then
    /usr/bin/osascript -e "display dialog \"8899 端口已被占用，BridgeDeck UI 未启动。\\n\\n$owners\" buttons {\"OK\"} with title \"BridgeDeck\"" >/dev/null 2>&1 || true
  else
    /usr/bin/osascript -e 'display dialog "BridgeDeck UI 启动超时。请查看 ~/Library/Logs/bridgedeck-app.log。" buttons {"OK"} with title "BridgeDeck"' >/dev/null 2>&1 || true
  fi
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
  CODEX_BRIDGE_SCRIPT="$RESOURCE_DIR/local_codex_bridge.py" "$(python_bin)" "$RESOURCE_DIR/bridgedeck.py" --local-bridge start >> "$LOG_FILE" 2>&1 &
  /usr/bin/osascript -e 'display notification "8876 Local Bridge 已启动或已在运行" with title "BridgeDeck"' >/dev/null 2>&1 || true
}

write_install_state() {
  local status="$1"
  local ok="$2"
  /bin/mkdir -p "$(/usr/bin/dirname "$INSTALL_STATE")"
  /bin/cat > "$INSTALL_STATE" <<STATE
{"status":"$status","ok":$ok,"checked_at":"$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')","root":"$RESOURCE_DIR"}
STATE
}

run_install_scan_background() {
  log_event "install_scan_background"
  "$(python_bin)" "$RESOURCE_DIR/bridgedeck.py" --install-scan --write-install-state >> "$LOG_FILE" 2>&1 &
}

first_install_scan_prompt() {
  if [[ -f "$INSTALL_STATE" ]]; then
    return 0
  fi
  choice="$(/usr/bin/osascript <<'APPLESCRIPT' 2>/dev/null || true
button returned of (display dialog "首次打开 BridgeDeck。建议先运行安装扫描：Python 编译检查、打包脚本语法检查、/Applications 版本检查。" buttons {"取消", "后台扫描并打开 UI", "直接打开 UI"} default button "直接打开 UI" cancel button "取消" with title "BridgeDeck 安装扫描")
APPLESCRIPT
)"
  log_event "first_install_choice=${choice:-<empty>}"
  case "$choice" in
    "后台扫描并打开 UI")
      write_install_state "pending" "true"
      run_install_scan_background
      ;;
    "直接打开 UI"|"")
      write_install_state "skipped" "true"
      ;;
    *)
      exit 0
      ;;
  esac
}

first_install_scan_prompt

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

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_DIR" >/dev/null
fi

/usr/bin/hdiutil create -volname "$APP_NAME" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG"
echo "$DMG"
