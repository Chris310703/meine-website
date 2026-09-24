"""Tests für „Kalender per Link“ (iCal/ICS, z. B. FamilyWall)."""

from datetime import date, datetime, timedelta

import pytest

from app.services import ics_calendars as ics

TODAY = date.today()


def _ics() -> bytes:
    d = TODAY.strftime("%Y%m%d")
    tomorrow = (TODAY + timedelta(days=1)).strftime("%Y%m%d")
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FamilyWall//DE
BEGIN:VEVENT
UID:training-1
SUMMARY:Fußballtraining
DTSTART;TZID=Europe/Berlin:{d}T180000
DTEND;TZID=Europe/Berlin:{d}T193000
RRULE:FREQ=WEEKLY;COUNT=4
LOCATION:Sportplatz
END:VEVENT
BEGIN:VEVENT
UID:geburtstag-1
SUMMARY:Geburtstag Oma
DTSTART;VALUE=DATE:{tomorrow}
DTEND;VALUE=DATE:{(TODAY + timedelta(days=2)).strftime("%Y%m%d")}
END:VEVENT
BEGIN:VEVENT
UID:abgesagt-1
SUMMARY:Abgesagt
STATUS:CANCELLED
DTSTART:{d}T090000Z
DTEND:{d}T100000Z
END:VEVENT
BEGIN:VEVENT
UID:utc-1
SUMMARY:Arzttermin
DTSTART:{tomorrow}T080000Z
DTEND:{tomorrow}T083000Z
END:VEVENT
END:VCALENDAR
""".encode()


def test_normalize_url():
    assert ics.normalize_url("webcal://example.org/cal.ics") == "https://example.org/cal.ics"
    assert ics.normalize_url(" https://x.de/a.ics ") == "https://x.de/a.ics"
    with pytest.raises(ics.IcsError):
        ics.normalize_url("kein-link")


def test_parse_events_expands_recurrence_and_skips_cancelled():
    events = ics.parse_events(_ics(), TODAY - timedelta(days=1), TODAY + timedelta(days=40))
    titles = [e["title"] for e in events]
    assert titles.count("Fußballtraining") == 4
    assert "Abgesagt" not in titles
    birthday = next(e for e in events if e["title"] == "Geburtstag Oma")
    assert birthday["all_day"] is True
    training = min((e for e in events if e["title"] == "Fußballtraining"), key=lambda e: e["start"])
    assert training["start"] == datetime.combine(TODAY, datetime.min.time()).replace(hour=18)
    assert training["location"] == "Sportplatz"
    # UTC-Zeit wird in Ortszeit umgerechnet (Europe/Berlin: +1 oder +2 Stunden)
    doctor = next(e for e in events if e["title"] == "Arzttermin")
    assert doctor["start"].hour in (9, 10)
    assert len({e["uid"] for e in events}) == len(events)


def test_feed_refresh_stores_events_and_blocks_study_time(db, monkeypatch):
    from app.models import CalendarEvent

    monkeypatch.setattr(ics, "_download", lambda url: _ics())
    feed = ics.add_feed(db, "FamilyWall", "webcal://example.org/family.ics")
    assert feed["url"].startswith("https://")
    result = ics.refresh_all(db)
    assert result["changed"] is True
    rows = db.query(CalendarEvent).filter(CalendarEvent.calendar_id == ics.calendar_key(feed["id"])).all()
    assert len(rows) >= 5
    assert ics.feeds(db)[0]["events"] == len(rows)
    assert ics.feeds(db)[0]["last_error"] == ""
    # Zweiter Abruf ohne Änderung → nichts neu geplant
    assert ics.refresh_all(db)["changed"] is False
    ics.remove_feed(db, feed["id"])
    assert db.query(CalendarEvent).count() == 0
    assert ics.feeds(db) == []


def test_feed_error_is_reported(db, monkeypatch):
    def broken(url):
        raise ics.IcsError("Der Link funktioniert nicht (Fehler 404) – bitte neu kopieren.")

    monkeypatch.setattr(ics, "_download", broken)
    ics.add_feed(db, "Kaputt", "https://example.org/x.ics")
    ics.refresh_all(db)
    assert "404" in ics.feeds(db)[0]["last_error"]


def test_api_hides_full_link(client, monkeypatch):
    monkeypatch.setattr(ics, "refresh_async", lambda: False)
    r = client.post("/api/ics", json={"name": "FamilyWall", "url": "webcal://example.org/" + "a" * 60 + ".ics"})
    assert r.status_code == 200
    listed = client.get("/api/ics").json()["feeds"][0]
    assert listed["url"].endswith("…")
    assert "ics_calendars" not in client.get("/api/settings").json()
    assert client.post("/api/ics", json={"url": "ftp://nope.example"}).status_code == 400
    assert client.delete(f"/api/ics/{listed['id']}").json() == {"ok": True}
