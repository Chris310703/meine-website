"""Kalender per Link (iCal/ICS), z. B. FamilyWall: Termine direkt abrufen, ohne Umweg über Google."""

from __future__ import annotations

import logging
import threading
import time as _time
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..database import SessionLocal
from ..models import CalendarEvent

log = logging.getLogger("lifeos.ics")

REFRESH_MINUTES = 15
DAYS_BACK = 14
DAYS_FORWARD = 120
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) LifeOS-Kalender/1.0"

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "last_run": None}


class IcsError(Exception):
    pass


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.lower().startswith(("http://", "https://")):
        raise IcsError("Der Link muss mit webcal://, https:// oder http:// beginnen.")
    return url


def calendar_key(feed_id: str) -> str:
    return f"ics:{feed_id}"


def feeds(db: Session) -> list[dict[str, Any]]:
    return list(settings_store.get(db, "ics_calendars") or [])


def _save_feeds(db: Session, items: list[dict[str, Any]]) -> None:
    settings_store.set_value(db, "ics_calendars", items)


def add_feed(db: Session, name: str, url: str) -> dict[str, Any]:
    item = {"id": uuid.uuid4().hex[:10], "name": name.strip() or "Kalender", "url": normalize_url(url), "last_fetched": None, "last_error": "", "events": 0}
    _save_feeds(db, feeds(db) + [item])
    return item


def remove_feed(db: Session, feed_id: str) -> None:
    _save_feeds(db, [f for f in feeds(db) if f["id"] != feed_id])
    db.execute(delete(CalendarEvent).where(CalendarEvent.calendar_id == calendar_key(feed_id)))
    db.commit()


def _to_local(value: Any, tz: ZoneInfo) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(tz).replace(tzinfo=None)
        return value, False
    if isinstance(value, date):
        return datetime.combine(value, time.min), True
    raise IcsError(f"Unbekanntes Datumsformat: {value!r}")


def parse_events(content: bytes, start: date, end: date) -> list[dict[str, Any]]:
    """Liest eine ICS-Datei und liefert alle Termine (inkl. Wiederholungen) im Zeitraum."""
    import icalendar
    import recurring_ical_events

    try:
        cal = icalendar.Calendar.from_ical(content)
    except Exception as exc:
        raise IcsError(f"Die Datei ist kein gültiger Kalender: {exc}") from exc
    tz = ZoneInfo(config.TIMEZONE)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end + timedelta(days=1)):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        dtstart = ev.get("DTSTART")
        if dtstart is None:
            continue
        s, all_day = _to_local(dtstart.dt, tz)
        if ev.get("DTEND") is not None:
            e, _ = _to_local(ev.get("DTEND").dt, tz)
        elif ev.get("DURATION") is not None:
            e = s + ev.get("DURATION").dt
        else:
            e = s + (timedelta(days=1) if all_day else timedelta(hours=1))
        if e <= s:
            e = s + (timedelta(days=1) if all_day else timedelta(minutes=30))
        uid = str(ev.get("UID", "")) or f"{s.isoformat()}-{ev.get('SUMMARY', '')}"
        out.append(
            {
                "uid": f"{uid}@{s.isoformat()}",
                "title": str(ev.get("SUMMARY", "")) or "(ohne Titel)",
                "location": str(ev.get("LOCATION", "") or ""),
                "start": s,
                "end": e,
                "all_day": all_day,
            }
        )
    return out


def _download(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    if resp.status_code in (401, 403, 404):
        raise IcsError(f"Der Link funktioniert nicht (Fehler {resp.status_code}) – bitte neu kopieren.")
    resp.raise_for_status()
    return resp.content


def refresh_feed(db: Session, feed: dict[str, Any]) -> bool:
    """Aktualisiert einen Kalender. Rückgabe: True, wenn sich Termine geändert haben."""
    today = date.today()
    start, end = today - timedelta(days=DAYS_BACK), today + timedelta(days=DAYS_FORWARD)
    key = calendar_key(feed["id"])
    events = parse_events(_download(feed["url"]), start, end)
    old = {
        (e.google_id, e.start, e.end, e.title)
        for e in db.query(CalendarEvent).filter(CalendarEvent.calendar_id == key).all()
    }
    new = {(e["uid"], e["start"], e["end"], e["title"]) for e in events}
    if old == new:
        return False
    db.execute(delete(CalendarEvent).where(CalendarEvent.calendar_id == key))
    seen: set[str] = set()
    for e in events:
        if e["uid"] in seen:
            continue
        seen.add(e["uid"])
        db.add(
            CalendarEvent(
                google_id=e["uid"][:250],
                calendar_id=key,
                calendar_name=feed["name"],
                title=e["title"][:300],
                start=e["start"],
                end=e["end"],
                all_day=e["all_day"],
                location=e["location"][:300],
            )
        )
    db.commit()
    return True


def refresh_all(db: Session) -> dict[str, Any]:
    items = feeds(db)
    changed = False
    for f in items:
        try:
            if refresh_feed(db, f):
                changed = True
            f["last_error"] = ""
            f["events"] = db.query(CalendarEvent).filter(CalendarEvent.calendar_id == calendar_key(f["id"])).count()
        except IcsError as exc:
            f["last_error"] = str(exc)
        except Exception as exc:
            f["last_error"] = f"Kalender nicht erreichbar: {exc}"
        f["last_fetched"] = datetime.now().replace(microsecond=0).isoformat()
    # Status in die aktuelle Liste übernehmen (falls währenddessen Kalender hinzugefügt/gelöscht wurden)
    by_id = {f["id"]: f for f in items}
    _save_feeds(db, [by_id.get(f["id"], f) for f in feeds(db)])
    if changed:
        from . import google_calendar, study_service

        study_service.replan(db)
        google_calendar.push_if_enabled(db)
    return {"changed": changed, "feeds": len(items)}


def refresh_async() -> bool:
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
    threading.Thread(target=_run, daemon=True).start()
    return True


def _run() -> None:
    try:
        with SessionLocal() as db:
            if feeds(db):
                _state["last_result"] = refresh_all(db)
    except Exception:  # pragma: no cover
        log.exception("Kalender-Abruf fehlgeschlagen")
    finally:
        _state["running"] = False
        _state["last_run"] = datetime.now().replace(microsecond=0).isoformat()


def status() -> dict[str, Any]:
    return dict(_state)


def start_background_loop() -> None:
    """Holt alle verknüpften Kalender beim Start und danach alle 15 Minuten."""

    def loop() -> None:
        while True:
            refresh_async()
            _time.sleep(REFRESH_MINUTES * 60)

    threading.Thread(target=loop, daemon=True, name="ics-refresh").start()
