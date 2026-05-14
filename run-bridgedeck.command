#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_URL="http://127.0.0.1:8899"
LOG_DIR="$HOME/Library/Logs"
LOG_FILE="$LOG_DIR/bridgedeck-app.log"
mkdir -p "$LOG_DIR"

log_event() {
  /bin/echo "$(/bin/date '+%Y-%m-%d %H:%M:%S') run-command: $*" >> "$LOG_FILE"
}

ui_running() {
  /usr/bin/curl -fsS -H "X-CCSBT-Token: probe" "$APP_URL/" >/dev/null 2>&1
}

open_ui() {
  log_event "open_ui $APP_URL"
  open "$APP_URL"
}

stop_ui_keep_bridge() {
  log_event "stop_ui_keep_bridge"
  for pid in $(/usr/sbin/lsof -tiTCP:8899 -sTCP:LISTEN 2>/dev/null); do
    cmd="$(/bin/ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"bridgedeck.py"* ]]; then
      /bin/kill "$pid" 2>/dev/null || true
    fi
  done
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
  esac
  exit 0
fi

log_event "launcher_start ui_running=0"
choice="$(/usr/bin/osascript <<'APPLESCRIPT' 2>/dev/null || true
button returned of (display dialog "BridgeDeck UI 未运行。要打开配置页，还是只启动 8876 Local Bridge？" buttons {"取消", "只启动 Bridge", "打开 UI"} default button "打开 UI" cancel button "取消" with title "BridgeDeck")
APPLESCRIPT
)"
log_event "dialog_choice=${choice:-<empty>}"
case "$choice" in
  "只启动 Bridge")
    exec /usr/bin/env python3 "$SCRIPT_DIR/bridgedeck.py" --local-bridge start
    ;;
  "打开 UI")
    (sleep 1; open "$APP_URL") &
    exec /usr/bin/env python3 "$SCRIPT_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899
    ;;
  "")
    log_event "dialog_empty_fallback=start_ui"
    (sleep 1; open "$APP_URL") &
    exec /usr/bin/env python3 "$SCRIPT_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899
    ;;
esac
