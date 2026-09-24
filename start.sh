#!/usr/bin/env bash
# ------------------------------------------------------------------
#  Life OS starten:   ./start.sh
#  Entwicklermodus:   ./start.sh dev   (Hot-Reload auf http://localhost:5173)
#  Tests ausführen:   ./start.sh test
# ------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
MODE="${1:-start}"

cyan() { printf "\033[36m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }

# --- .env anlegen, falls sie fehlt --------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  cyan "→ .env aus .env.example angelegt (Zugangsdaten kannst du später eintragen)."
fi
PORT="$(grep -E '^LIFEOS_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="${PORT:-8000}"

# --- Python finden (mind. 3.10) -----------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$(command -v "$candidate")"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  red "Python 3.10 oder neuer wurde nicht gefunden. Bitte installieren: https://www.python.org/downloads/"
  exit 1
fi

# --- Node prüfen ----------------------------------------------------
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  red "Node.js wurde nicht gefunden. Bitte die LTS-Version installieren: https://nodejs.org/"
  exit 1
fi
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a===20&&b>=19)||a>=22?0:1)'; then
  red "Node.js $(node -v) ist zu alt. Bitte Node.js 22 (LTS) oder neuer installieren: https://nodejs.org/"
  exit 1
fi

hash_file() { "$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }

# --- Backend: virtuelle Umgebung & Pakete ---------------------------
VENV="$ROOT/backend/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  cyan "→ Lege Python-Umgebung an …"
  "$PY" -m venv "$VENV"
fi
REQ="backend/requirements.txt"
if [ "$MODE" = "test" ] || [ "$MODE" = "dev" ]; then REQ="backend/requirements-dev.txt"; fi
STAMP="$VENV/.deps-stamp-$(basename "$REQ")"
REQ_HASH="$(hash_file "$REQ")$(hash_file backend/requirements.txt)"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REQ_HASH" ]; then
  cyan "→ Installiere Python-Pakete (einmalig, dauert etwas) …"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r "$REQ"
  echo "$REQ_HASH" > "$STAMP"
fi

if [ "$MODE" = "test" ]; then
  cd backend
  exec "$VENV/bin/python" -m pytest -q
fi

# --- Frontend: Pakete & Build --------------------------------------
cd "$ROOT/frontend"
LOCK_HASH="$(hash_file package.json)"
if [ -f package-lock.json ]; then LOCK_HASH="$LOCK_HASH$(hash_file package-lock.json)"; fi
if [ ! -d node_modules ] || [ ! -f node_modules/.lifeos-stamp ] || [ "$(cat node_modules/.lifeos-stamp)" != "$LOCK_HASH" ]; then
  cyan "→ Installiere Frontend-Pakete (einmalig) …"
  npm install --no-audit --no-fund --loglevel=error
  echo "$LOCK_HASH" > node_modules/.lifeos-stamp
fi

if [ "$MODE" = "dev" ]; then
  cyan "→ Entwicklermodus: Backend :$PORT (Reload) + Frontend http://localhost:5173"
  cd "$ROOT/backend"
  "$VENV/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT" &
  BACK_PID=$!
  trap 'kill $BACK_PID 2>/dev/null || true' EXIT INT TERM
  cd "$ROOT/frontend"
  npx vite --port 5173 --open
  exit 0
fi

if [ ! -f dist/index.html ] || [ -n "$(find src index.html package.json vite.config.js public -newer dist/index.html -print -quit 2>/dev/null)" ]; then
  cyan "→ Baue die Oberfläche …"
  npx vite build --logLevel error
fi

# --- App starten ----------------------------------------------------
cd "$ROOT/backend"
URL="http://localhost:$PORT"
cyan ""
cyan "  ╔══════════════════════════════════════════╗"
cyan "  ║  LIFE OS läuft auf  $URL"
cyan "  ║  Beenden mit  Ctrl + C                   ║"
cyan "  ╚══════════════════════════════════════════╝"
cyan ""
( sleep 2.5
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  fi ) &
exec "$VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
