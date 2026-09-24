#!/usr/bin/env bash
# ------------------------------------------------------------------
#  Life OS aktualisieren:   bash update.sh
#  Lädt die neueste Version von GitHub und ersetzt den Programmcode.
#  Deine Daten (backend/data), die .env und installierte Pakete bleiben erhalten.
# ------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
REPO="Chris310703/meine-website"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ Lade die neueste Version …"
curl -fsSL -o "$TMP/lifeos.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
unzip -q "$TMP/lifeos.zip" -d "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"

rsync -a \
  --exclude ".env" \
  --exclude "backend/data/" \
  --exclude "backend/.venv/" \
  --exclude "frontend/node_modules/" \
  "$SRC/" "$ROOT/"

# Oberfläche beim nächsten Start neu bauen
rm -rf "$ROOT/frontend/dist"

echo "✓ Aktualisiert. Starte die App neu (Terminal-Fenster schließen, dann Symbol „Life OS“ anklicken)."
