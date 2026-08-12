#!/usr/bin/env bash
# Package gui/ (the SwiftUI menubar app) into a real, double-clickable
# Zero.app bundle for local dev/distribution.
#
# NOTE: packaging/build/ and packaging/dist/ are legacy py2app output for a
# retired Python UI — do not build into them. This script's output lives
# under packaging/macos-app/ instead, which is separately gitignored.
#
# Usage: packaging/build_macos_app.sh [output_dir]
#   output_dir defaults to packaging/macos-app

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GUI_DIR="$ROOT_DIR/gui"
OUT_DIR="${1:-$ROOT_DIR/packaging/macos-app}"
APP="$OUT_DIR/Zero.app"

if [ ! -f "$GUI_DIR/Package.swift" ]; then
    echo "error: $GUI_DIR/Package.swift not found" >&2
    exit 1
fi

echo "==> Building ZeroUI (release)"
swift build --package-path "$GUI_DIR" -c release
BIN_DIR="$(swift build --package-path "$GUI_DIR" -c release --show-bin-path)"
BIN="$BIN_DIR/ZeroUI"

if [ ! -f "$BIN" ]; then
    echo "error: expected binary not found at $BIN" >&2
    exit 1
fi

echo "==> Assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Zero"

# Only reference an icon file if one actually exists — a CFBundleIconFile
# pointing at a missing resource makes Finder show the generic icon anyway,
# but there's no reason to claim a file we didn't ship.
ICON_SRC="$GUI_DIR/Sources/ZeroUI/Resources/Zero.icns"
ICON_KEY=""
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APP/Contents/Resources/Zero.icns"
    ICON_KEY="    <key>CFBundleIconFile</key>
    <string>Zero</string>
"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>Zero</string>
    <key>CFBundleIdentifier</key>
    <string>computer.zero.menubar</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Zero</string>
    <key>CFBundleDisplayName</key>
    <string>Zero</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Zero</string>
${ICON_KEY}</dict>
</plist>
PLIST

printf 'APPL????' > "$APP/Contents/PkgInfo"

echo "==> Ad-hoc codesigning $APP"
codesign --force --deep -s - "$APP"

echo "==> Done: $APP"
echo "    Verify:  codesign -dv \"$APP\""
echo "    Launch:  open \"$APP\""
