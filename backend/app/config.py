"""Zentrale Konfiguration. Alle Geheimnisse kommen aus der .env-Datei im Projektordner."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# .env im Projektordner (neben start.sh) laden – existiert sie nicht, gelten die Standardwerte.
load_dotenv(PROJECT_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "ja", "yes", "on"}


DATA_DIR = Path(_env("LIFEOS_DATA_DIR") or (BACKEND_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = _env("LIFEOS_DATABASE_URL") or f"sqlite:///{DATA_DIR / 'lifeos.db'}"

# Beispieldaten beim ersten Start anlegen
SEED_DEMO_DATA = _env_bool("LIFEOS_DEMO_DATA", True)
# Automatischer Garmin-Sync beim Start
AUTO_SYNC_ON_START = _env_bool("LIFEOS_AUTO_SYNC", True)

TIMEZONE = _env("LIFEOS_TIMEZONE", "Europe/Berlin")

# --- Garmin ---
GARMIN_EMAIL = _env("GARMIN_EMAIL")
GARMIN_PASSWORD = _env("GARMIN_PASSWORD")
GARMIN_TOKEN_DIR = DATA_DIR / "garmin_tokens"

# --- Google Kalender ---
GOOGLE_CLIENT_SECRET_FILE = Path(
    _env("GOOGLE_CLIENT_SECRET_FILE") or (DATA_DIR / "google_client_secret.json")
)
GOOGLE_TOKEN_FILE = DATA_DIR / "google_token.json"
PORT = int(_env("LIFEOS_PORT", "8000") or 8000)
PUBLIC_BASE_URL = _env("LIFEOS_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
FRONTEND_URL = _env("LIFEOS_FRONTEND_URL", PUBLIC_BASE_URL).rstrip("/")
GOOGLE_REDIRECT_URI = f"{PUBLIC_BASE_URL}/api/google/callback"
STUDY_CALENDAR_NAME = "Life OS – Lernplan"

# --- Claude API ---
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5")

FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
