#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BridgeDeck"
BUILD_DIR="$ROOT/dist"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
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
cp "$ROOT/README.md" "$RESOURCES/README.md"
cp "$ROOT/SECURITY.md" "$RESOURCES/SECURITY.md"
cp "$ROOT/CONTRIBUTING.md" "$RESOURCES/CONTRIBUTING.md"
cp "$ROOT/CHANGELOG.md" "$RESOURCES/CHANGELOG.md"
cp "$ROOT/OPEN_SOURCE_CHECKLIST.md" "$RESOURCES/OPEN_SOURCE_CHECKLIST.md"
cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"

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
(sleep 1; open "http://127.0.0.1:8899") &
exec /usr/bin/python3 "$RESOURCE_DIR/bridgedeck.py" --host 127.0.0.1 --port 8899
LAUNCHER
chmod +x "$MACOS/launcher"

/usr/bin/hdiutil create -volname "$APP_NAME" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG"
echo "$DMG"
