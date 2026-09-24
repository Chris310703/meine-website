#!/usr/bin/env bash
# ------------------------------------------------------------------
#  Legt das Programm „Life OS“ mit Icon auf dem Schreibtisch an.
#  Einmal ausführen:   bash desktop-icon.sh
#  Klick auf das Symbol: startet die App (falls nötig) und öffnet sie im Browser.
#  Wurde der Projektordner verschoben, das Skript einfach erneut ausführen.
# ------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

if [ "$(uname)" != "Darwin" ]; then
  echo "Dieses Skript ist für macOS gedacht."
  exit 1
fi

PORT="$(grep -E '^LIFEOS_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="${PORT:-8000}"
APP="$HOME/Desktop/Life OS.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# AppleScript: Läuft die App schon → nur Browser öffnen, sonst im Terminal starten
cat > "$TMP/lifeos.applescript" <<EOF
on run
	set appRoot to "$ROOT"
	try
		do shell script "curl -s -f -m 2 http://127.0.0.1:$PORT/api/health > /dev/null"
		open location "http://localhost:$PORT"
	on error
		tell application "Terminal"
			activate
			do script "cd " & quoted form of appRoot & " && bash start.sh"
		end tell
	end try
end run
EOF

rm -rf "$APP"
osacompile -o "$APP" "$TMP/lifeos.applescript"

# Icon aus assets/lifeos-icon.png erzeugen
ICON_PNG="$ROOT/assets/lifeos-icon.png"
if [ -f "$ICON_PNG" ]; then
  SET="$TMP/lifeos.iconset"
  mkdir -p "$SET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_PNG" --out "$SET/icon_${size}x${size}.png" > /dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$ICON_PNG" --out "$SET/icon_${size}x${size}@2x.png" > /dev/null
  done
  iconutil -c icns "$SET" -o "$TMP/lifeos.icns"
  cp "$TMP/lifeos.icns" "$APP/Contents/Resources/applet.icns"
  rm -f "$APP/Contents/Resources/Assets.car"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
fi

xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
touch "$APP"

echo ""
echo "✓ „Life OS“ liegt jetzt auf deinem Schreibtisch."
echo "  Doppelklick darauf startet die App und öffnet http://localhost:$PORT"
echo "  Tipp: Symbol ins Dock ziehen, dann reicht ein einzelner Klick."
