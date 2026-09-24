"""Kalender (Wochen-/Monatsansicht) und Google-Kalender-Verbindung."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..database import get_db
from ..services import agenda, google_calendar
from ..utils import parse_date

router = APIRouter(prefix="/api", tags=["Kalender"])


@router.get("/calendar")
def calendar(start: str | None = None, end: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = parse_date(start, date.today() - timedelta(days=date.today().weekday()))
    e = parse_date(end, s + timedelta(days=6))
    if (e - s).days > 62:
        raise HTTPException(status_code=400, detail="Zeitraum zu groß (max. 62 Tage).")
    return {
        "start": s.isoformat(),
        "end": e.isoformat(),
        "items": agenda.serialize(agenda.agenda(db, s, e)),
        "google_connected": google_calendar.is_connected(),
    }


# ---------------------------------------------------------------- Google


@router.get("/google/status")
def google_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return google_calendar.status(db)


@router.get("/google/auth-url")
def google_auth_url() -> dict[str, str]:
    try:
        return {"url": google_calendar.auth_url()}
    except google_calendar.GoogleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/google/callback", include_in_schema=False)
def google_callback(state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    target = f"{config.FRONTEND_URL}/einstellungen"
    if error:
        return RedirectResponse(f"{target}?google=abgebrochen")
    try:
        google_calendar.handle_callback(state, code)
    except Exception as exc:  # verständliche Seite statt Stacktrace
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;background:#070b10;color:#e6edf3;padding:40px'>"
            f"<h2>Google-Verbindung fehlgeschlagen</h2><p>{exc}</p>"
            f"<p><a style='color:#22d3ee' href='{target}'>Zurück zu den Einstellungen</a></p></body></html>",
            status_code=400,
        )
    if not settings_store.get(db, "google_read_calendars"):
        settings_store.set_value(db, "google_read_calendars", ["primary"])
    google_calendar.start_background_sync()
    return RedirectResponse(f"{target}?google=verbunden")


@router.post("/google/disconnect")
def google_disconnect(db: Session = Depends(get_db)) -> dict[str, Any]:
    google_calendar.disconnect(db)
    return google_calendar.status(db)


@router.get("/google/calendars")
def google_calendars(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        cals = google_calendar.list_calendars()
    except google_calendar.GoogleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google-Kalender nicht erreichbar: {exc}") from exc
    study_id = settings_store.get(db, "google_study_calendar_id")
    primary = next((c["id"] for c in cals if c["primary"]), "primary")
    selected = [primary if x == "primary" else x for x in (settings_store.get(db, "google_read_calendars") or ["primary"])]
    return {"calendars": [c for c in cals if c["id"] != study_id], "selected": selected}


class CalendarSelection(BaseModel):
    ids: list[str]


@router.put("/google/calendars")
def select_calendars(payload: CalendarSelection, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings_store.set_value(db, "google_read_calendars", payload.ids)
    google_calendar.start_background_sync(pull=True, push=False)
    return google_calendar.status(db)


@router.post("/google/sync")
def google_sync(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not google_calendar.is_connected():
        raise HTTPException(status_code=400, detail="Google Kalender ist nicht verbunden (Einstellungen → Verbindungen).")
    started = google_calendar.start_background_sync()
    return {"started": started, "status": google_calendar.status(db)}
