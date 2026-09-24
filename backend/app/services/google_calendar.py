"""Google Kalender: OAuth-Login, Termine lesen, Lernplan-Kalender schreiben und aktualisieren."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..database import SessionLocal
from ..models import CalendarEvent, GoogleDeletion, PlannedWorkout, StudyBlock, SyncLog
from . import agenda

log = logging.getLogger("lifeos.google")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Lokaler OAuth-Rückruf läuft über http://localhost – für oauthlib erlauben
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

_pending_flows: dict[str, Any] = {}
_state: dict[str, Any] = {"running": False, "last_error": "", "last_message": ""}
_lock = threading.Lock()


class GoogleError(Exception):
    pass


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def has_client_secret() -> bool:
    return config.GOOGLE_CLIENT_SECRET_FILE.exists()


def is_connected() -> bool:
    return config.GOOGLE_TOKEN_FILE.exists()


def status(db: Session) -> dict[str, Any]:
    last_ok = (
        db.query(SyncLog)
        .filter(SyncLog.service == "google", SyncLog.status == "ok")
        .order_by(SyncLog.finished_at.desc())
        .first()
    )
    last = db.query(SyncLog).filter(SyncLog.service == "google").order_by(SyncLog.started_at.desc()).first()
    return {
        "has_client_secret": has_client_secret(),
        "client_secret_path": str(config.GOOGLE_CLIENT_SECRET_FILE),
        "connected": is_connected(),
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "read_calendars": settings_store.get(db, "google_read_calendars") or [],
        "study_calendar_id": settings_store.get(db, "google_study_calendar_id"),
        "auto_push": bool(settings_store.get(db, "google_auto_push", True)),
        "sync": dict(_state),
        "last_sync": last_ok.finished_at.isoformat() if last_ok and last_ok.finished_at else None,
        "last_status": last.status if last else None,
        "last_log_message": last.message if last else "",
    }


# ---------------------------------------------------------------- OAuth


def auth_url() -> str:
    if not has_client_secret():
        raise GoogleError(
            f"Die Datei mit den Google-Zugangsdaten fehlt ({config.GOOGLE_CLIENT_SECRET_FILE}). "
            "Siehe README, Abschnitt „Google Kalender einrichten“."
        )
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        str(config.GOOGLE_CLIENT_SECRET_FILE), scopes=SCOPES, redirect_uri=config.GOOGLE_REDIRECT_URI
    )
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    _pending_flows[state] = flow
    return url


def handle_callback(state: str, code: str) -> None:
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise GoogleError("Die Anmeldung ist abgelaufen. Bitte in den Einstellungen erneut verbinden.")
    flow.fetch_token(code=code)
    creds = flow.credentials
    config.GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    try:
        os.chmod(config.GOOGLE_TOKEN_FILE, 0o600)
    except OSError:  # pragma: no cover
        pass


def disconnect(db: Session) -> None:
    if config.GOOGLE_TOKEN_FILE.exists():
        config.GOOGLE_TOKEN_FILE.unlink()
    settings_store.set_value(db, "google_study_calendar_id", None)
    for b in db.query(StudyBlock).filter(StudyBlock.google_event_id.isnot(None)).all():
        b.google_event_id = None
        b.google_hash = None
    for w in db.query(PlannedWorkout).filter(PlannedWorkout.google_event_id.isnot(None)).all():
        w.google_event_id = None
        w.google_hash = None
    db.execute(delete(GoogleDeletion))
    db.execute(delete(CalendarEvent).where(CalendarEvent.is_demo.is_(False), CalendarEvent.calendar_id.notlike("ics:%")))
    db.commit()


def _credentials():
    if not is_connected():
        raise GoogleError("Google Kalender ist nicht verbunden.")
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise GoogleError("Die Google-Anmeldung ist abgelaufen. Bitte in den Einstellungen neu verbinden.") from exc
        config.GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    return creds


def _service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=_credentials(), cache_discovery=False)


def list_calendars() -> list[dict[str, Any]]:
    svc = _service()
    items: list[dict[str, Any]] = []
    token = None
    while True:
        resp = svc.calendarList().list(pageToken=token).execute()
        for c in resp.get("items", []):
            items.append(
                {
                    "id": c["id"],
                    "name": c.get("summaryOverride") or c.get("summary", c["id"]),
                    "primary": bool(c.get("primary")),
                    "color": c.get("backgroundColor"),
                    "access": c.get("accessRole"),
                }
            )
        token = resp.get("nextPageToken")
        if not token:
            break
    return items


# ---------------------------------------------------------------- Lesen


def _to_local(value: dict[str, Any]) -> tuple[datetime, bool]:
    if "dateTime" in value:
        dt = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(_tz()).replace(tzinfo=None)
        return dt, False
    return datetime.combine(date.fromisoformat(value["date"]), time.min), True


def pull_events(db: Session, svc, days_back: int = 14, days_forward: int = 90) -> int:
    selected = settings_store.get(db, "google_read_calendars") or ["primary"]
    study_id = settings_store.get(db, "google_study_calendar_id")
    names = {c["id"]: c["name"] for c in list_calendars()}
    now = datetime.now(_tz())
    time_min = (now - timedelta(days=days_back)).isoformat()
    time_max = (now + timedelta(days=days_forward)).isoformat()
    window_start = (now - timedelta(days=days_back)).replace(tzinfo=None)
    count = 0

    # Beispieltermine beim ersten echten Abruf entfernen
    db.execute(delete(CalendarEvent).where(CalendarEvent.is_demo.is_(True)))

    for cal_id in selected:
        if cal_id == study_id:
            continue
        seen: set[str] = set()
        token = None
        while True:
            resp = (
                svc.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=2500,
                    pageToken=token,
                )
                .execute()
            )
            for ev in resp.get("items", []):
                if ev.get("status") == "cancelled" or "start" not in ev:
                    continue
                start, all_day = _to_local(ev["start"])
                end, _ = _to_local(ev.get("end", ev["start"]))
                row = (
                    db.query(CalendarEvent)
                    .filter(CalendarEvent.calendar_id == cal_id, CalendarEvent.google_id == ev["id"])
                    .one_or_none()
                )
                if row is None:
                    row = CalendarEvent(calendar_id=cal_id, google_id=ev["id"])
                    db.add(row)
                row.calendar_name = names.get(cal_id, cal_id)
                row.title = ev.get("summary", "")
                row.start, row.end, row.all_day = start, end, all_day
                row.location = ev.get("location", "")
                seen.add(ev["id"])
                count += 1
            token = resp.get("nextPageToken")
            if not token:
                break
        # Im Zeitfenster gelöschte Termine entfernen
        stale = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.calendar_id == cal_id, CalendarEvent.start >= window_start)
            .all()
        )
        for row in stale:
            if row.google_id not in seen:
                db.delete(row)
    # Kalender, die nicht mehr ausgewählt sind, aus dem Zwischenspeicher löschen
    db.execute(
        delete(CalendarEvent).where(
            CalendarEvent.is_demo.is_(False),
            CalendarEvent.calendar_id.notin_(list(selected)),
            CalendarEvent.calendar_id.notlike("ics:%"),  # Kalender per Link nicht anfassen
        )
    )
    db.commit()
    return count


# ---------------------------------------------------------------- Schreiben


def ensure_study_calendar(db: Session, svc) -> str:
    from googleapiclient.errors import HttpError

    cal_id = settings_store.get(db, "google_study_calendar_id")
    if cal_id:
        try:
            svc.calendars().get(calendarId=cal_id).execute()
            return cal_id
        except HttpError:
            log.info("Gespeicherter Lernplan-Kalender existiert nicht mehr – wird neu angelegt.")
    for c in list_calendars():
        if c["name"] == config.STUDY_CALENDAR_NAME and c["access"] == "owner":
            settings_store.set_value(db, "google_study_calendar_id", c["id"])
            return c["id"]
    created = svc.calendars().insert(body={"summary": config.STUDY_CALENDAR_NAME, "timeZone": config.TIMEZONE}).execute()
    settings_store.set_value(db, "google_study_calendar_id", created["id"])
    # Neuer Kalender → alle Verknüpfungen zurücksetzen
    for b in db.query(StudyBlock).filter(StudyBlock.google_event_id.isnot(None)).all():
        b.google_event_id, b.google_hash = None, None
    for w in db.query(PlannedWorkout).filter(PlannedWorkout.google_event_id.isnot(None)).all():
        w.google_event_id, w.google_hash = None, None
    db.commit()
    return created["id"]


def _event_body(summary: str, start: datetime, end: datetime, description: str, color_id: str, kind: str, local_id: int) -> dict[str, Any]:
    return {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": config.TIMEZONE},
        "colorId": color_id,
        "extendedProperties": {"private": {"lifeos_type": kind, "lifeos_id": str(local_id)}},
    }


def _hash(body: dict[str, Any]) -> str:
    key = f"{body['summary']}|{body['start']['dateTime']}|{body['end']['dateTime']}|{body['description']}|{body['colorId']}"
    return hashlib.sha1(key.encode()).hexdigest()


def block_body(b: StudyBlock) -> dict[str, Any]:
    icon = {"lernen": "📚", "wiederholung": "🔁", "puffer": "🎯"}.get(b.kind, "📚")
    done = " ✓" if b.status == "erledigt" else ""
    kind = {"lernen": "Lernblock", "wiederholung": "Wiederholung", "puffer": "Prüfungsvorbereitung"}.get(b.kind, "Lernblock")
    desc = f"{kind} – {b.subject.name if b.subject else ''}\nErstellt von Life OS."
    if b.topic:
        desc = f"{kind} – {b.subject.name}\nThema: {b.topic.title}\nErstellt von Life OS."
    color = {"lernen": "6", "wiederholung": "5", "puffer": "11"}.get(b.kind, "6")
    return _event_body(f"{icon} {b.title}{done}", b.start, b.end, desc, color, "study_block", b.id)


def workout_body(w: PlannedWorkout) -> dict[str, Any]:
    start = datetime.combine(w.date, agenda.parse_hhmm(w.start_time))
    done = " ✓" if w.done else ""
    desc = (w.notes + "\n" if w.notes else "") + f"Training ({agenda.activity_label(w.type)}) – erstellt von Life OS."
    return _event_body(f"🏃 {w.title}{done}", start, start + timedelta(minutes=w.duration_min), desc, "10", "workout", w.id)


def push_study_plan(db: Session, svc) -> dict[str, int]:
    from googleapiclient.errors import HttpError

    cal_id = ensure_study_calendar(db, svc)
    stats = {"created": 0, "updated": 0, "deleted": 0}

    for d in db.query(GoogleDeletion).all():
        try:
            svc.events().delete(calendarId=cal_id, eventId=d.google_event_id).execute()
            stats["deleted"] += 1
        except HttpError as exc:
            if exc.resp.status not in (404, 410):
                raise
        db.delete(d)
    db.commit()

    since = datetime.combine(date.today() - timedelta(days=14), time.min)

    def upsert(obj, body):
        h = _hash(body)
        if obj.google_event_id and obj.google_hash == h:
            return
        try:
            if obj.google_event_id:
                svc.events().update(calendarId=cal_id, eventId=obj.google_event_id, body=body).execute()
                stats["updated"] += 1
            else:
                created = svc.events().insert(calendarId=cal_id, body=body).execute()
                obj.google_event_id = created["id"]
                stats["created"] += 1
        except HttpError as exc:
            if exc.resp.status in (404, 410) and obj.google_event_id:
                created = svc.events().insert(calendarId=cal_id, body=body).execute()
                obj.google_event_id = created["id"]
                stats["created"] += 1
            else:
                raise
        obj.google_hash = h

    for b in db.query(StudyBlock).filter(StudyBlock.start >= since).all():
        if b.status == "verpasst":
            if b.google_event_id:
                try:
                    svc.events().delete(calendarId=cal_id, eventId=b.google_event_id).execute()
                    stats["deleted"] += 1
                except HttpError:
                    pass
                b.google_event_id, b.google_hash = None, None
            continue
        upsert(b, block_body(b))
    db.commit()

    for w in db.query(PlannedWorkout).filter(PlannedWorkout.date >= since.date()).all():
        upsert(w, workout_body(w))
    db.commit()
    return stats


def delete_remote_event(db: Session, event_id: str | None) -> None:
    """Merkt einen Termin zum Löschen vor (wird beim nächsten Sync ausgeführt)."""
    if event_id:
        db.add(GoogleDeletion(google_event_id=event_id))


# ---------------------------------------------------------------- Sync


def sync_now(db: Session, pull: bool = True, push: bool = True) -> str:
    svc = _service()
    parts = []
    if pull:
        n = pull_events(db, svc)
        parts.append(f"{n} Termine gelesen")
    if push:
        stats = push_study_plan(db, svc)
        parts.append(
            f"Lernplan-Kalender: {stats['created']} neu, {stats['updated']} aktualisiert, {stats['deleted']} gelöscht"
        )
    return "; ".join(parts)


def start_background_sync(pull: bool = True, push: bool = True) -> bool:
    if not is_connected():
        return False
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, last_error="")
    threading.Thread(target=_run, args=(pull, push), daemon=True).start()
    return True


def _run(pull: bool, push: bool) -> None:
    with SessionLocal() as db:
        entry = SyncLog(service="google", status="läuft")
        db.add(entry)
        db.commit()
        try:
            entry.message = sync_now(db, pull=pull, push=push)
            entry.status = "ok"
            _state["last_message"] = entry.message
        except GoogleError as exc:
            entry.status, entry.message = "fehler", str(exc)
            _state["last_error"] = str(exc)
        except Exception as exc:
            log.exception("Google-Sync fehlgeschlagen")
            entry.status, entry.message = "fehler", f"Google-Sync fehlgeschlagen: {exc}"
            _state["last_error"] = entry.message
        finally:
            entry.finished_at = datetime.now().replace(microsecond=0)
            db.commit()
            _state["running"] = False


def push_if_enabled(db: Session) -> None:
    """Nach Änderungen am Lernplan automatisch in den Google-Kalender schreiben."""
    if is_connected() and settings_store.get(db, "google_auto_push", True):
        start_background_sync(pull=False, push=True)
