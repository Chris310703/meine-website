"""Life OS – FastAPI-Anwendung. Start: `./start.sh` im Projektordner."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, seed, settings_store
from .database import SessionLocal, init_db
from .routers import ROUTERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lifeos")


def startup_tasks() -> None:
    init_db()
    with SessionLocal() as db:
        if config.SEED_DEMO_DATA and not seed.is_seeded(db):
            log.info("Lege Beispieldaten an …")
            seed.seed_demo_data(db)

        # Verpasste Lernblöcke automatisch neu einplanen
        from .models import StudyBlock
        from .services import study_service

        now = datetime.now()
        if db.query(StudyBlock).filter(StudyBlock.status == "geplant", StudyBlock.end < now).first():
            log.info("Verpasste Lernblöcke gefunden – plane neu …")
            study_service.replan(db, now)

        # Automatischer Garmin-Sync beim Start
        from .services.garmin_sync import manager

        status = manager.status()
        if (
            config.AUTO_SYNC_ON_START
            and settings_store.get(db, "garmin_auto_sync", True)
            and (status["has_tokens"] or status["credentials_in_env"])
        ):
            log.info("Starte automatischen Garmin-Sync …")
            manager.start_sync()

        from .services import google_calendar

        if config.AUTO_SYNC_ON_START and google_calendar.is_connected():
            google_calendar.start_background_sync()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup_tasks()
    yield


app = FastAPI(title="Life OS", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in ROUTERS:
    app.include_router(router)


# ---------------------------------------------------------------- Frontend ausliefern

if (config.FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Unbekannter API-Pfad.")
    candidate = config.FRONTEND_DIST / full_path
    if full_path and candidate.is_file() and config.FRONTEND_DIST in candidate.resolve().parents:
        return FileResponse(candidate)
    index = config.FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "hinweis": "Das Frontend ist noch nicht gebaut. Starte die App mit ./start.sh "
        "oder öffne im Entwicklungsmodus http://localhost:5173."
    }
