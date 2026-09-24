"""Einheitliche Termin-Sicht: Google-Termine, Stundenplan, Lernblöcke, Trainings, Prüfungen."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import (
    Activity,
    CalendarEvent,
    PlannedWorkout,
    StudyBlock,
    Subject,
    TimetableEntry,
)

TYPE_COLORS = {
    "google": "#a78bfa",
    "stundenplan": "#22d3ee",
    "lernblock": "#fb923c",
    "training": "#4ade80",
    "pruefung": "#f472b6",
}

TYPE_LABELS = {
    "google": "Termin",
    "stundenplan": "Stundenplan",
    "lernblock": "Lernblock",
    "training": "Training",
    "pruefung": "Prüfung",
}

ACTIVITY_LABELS = {
    "running": "Laufen",
    "trail_running": "Trailrun",
    "treadmill_running": "Laufband",
    "track_running": "Bahnlauf",
    "cycling": "Radfahren",
    "road_biking": "Rennrad",
    "indoor_cycling": "Indoor-Rad",
    "mountain_biking": "Mountainbike",
    "swimming": "Schwimmen",
    "lap_swimming": "Schwimmen (Bahn)",
    "open_water_swimming": "Freiwasser",
    "strength_training": "Krafttraining",
    "walking": "Gehen",
    "hiking": "Wandern",
    "yoga": "Yoga",
    "hiit": "HIIT",
    "cardio": "Cardio",
    "indoor_cardio": "Cardio",
    "other": "Sonstiges",
}


def activity_label(type_key: str) -> str:
    return ACTIVITY_LABELS.get(type_key, type_key.replace("_", " ").title())


def parse_hhmm(value: str) -> time:
    h, m = (value or "00:00").split(":")[:2]
    return time(int(h), int(m))


def _semester_bounds(db: Session) -> tuple[date | None, date | None]:
    sem = settings_store.get(db, "semester") or {}
    start = date.fromisoformat(sem["start"]) if sem.get("start") else None
    end = date.fromisoformat(sem["end"]) if sem.get("end") else None
    return start, end


def entry_occurs_on(entry: TimetableEntry, day: date, sem_start: date | None, sem_end: date | None) -> bool:
    if day.weekday() != entry.weekday:
        return False
    first = entry.valid_from or sem_start
    last = entry.valid_until or sem_end
    if first and day < first:
        return False
    if last and day > last:
        return False
    interval = max(1, entry.interval_weeks or 1)
    if interval > 1:
        anchor = first or date(2020, 1, 6)
        anchor_monday = anchor - timedelta(days=anchor.weekday())
        weeks = (day - anchor_monday).days // 7
        if weeks % interval != 0:
            return False
    return True


def timetable_occurrences(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    sem_start, sem_end = _semester_bounds(db)
    entries = db.query(TimetableEntry).all()
    items: list[dict[str, Any]] = []
    day = start
    while day <= end:
        for e in entries:
            if not entry_occurs_on(e, day, sem_start, sem_end):
                continue
            s = datetime.combine(day, parse_hhmm(e.start_time))
            t = datetime.combine(day, parse_hhmm(e.end_time))
            items.append(
                {
                    "id": f"tt-{e.id}-{day.isoformat()}",
                    "source_id": e.id,
                    "type": "stundenplan",
                    "title": e.title,
                    "subtitle": " · ".join(x for x in (e.kind, e.room, e.lecturer) if x),
                    "start": s,
                    "end": t,
                    "all_day": False,
                    "color": TYPE_COLORS["stundenplan"],
                    "subject_color": e.color or (e.subject.color if e.subject else None),
                    "location": e.room,
                    "kind": e.kind,
                }
            )
        day += timedelta(days=1)
    return items


def agenda(db: Session, start: date, end: date, include_activities: bool = True) -> list[dict[str, Any]]:
    """Alle Einträge im Zeitraum [start, end] (inklusive)."""
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    items: list[dict[str, Any]] = []

    for ev in (
        db.query(CalendarEvent)
        .filter(CalendarEvent.start < end_dt, CalendarEvent.end > start_dt)
        .all()
    ):
        items.append(
            {
                "id": f"g-{ev.id}",
                "source_id": ev.id,
                "type": "google",
                "title": ev.title or "(ohne Titel)",
                "subtitle": ev.calendar_name,
                "start": ev.start,
                "end": ev.end,
                "all_day": ev.all_day,
                "color": TYPE_COLORS["google"],
                "location": ev.location,
            }
        )

    items.extend(timetable_occurrences(db, start, end))

    for b in (
        db.query(StudyBlock)
        .filter(StudyBlock.start < end_dt, StudyBlock.end > start_dt)
        .all()
    ):
        kind = {"lernen": "Lernen", "wiederholung": "Wiederholung", "puffer": "Puffer"}.get(b.kind, b.kind)
        items.append(
            {
                "id": f"sb-{b.id}",
                "source_id": b.id,
                "type": "lernblock",
                "title": b.title or (b.subject.name if b.subject else "Lernblock"),
                "subtitle": f"{kind} · {b.subject.name if b.subject else ''}",
                "start": b.start,
                "end": b.end,
                "all_day": False,
                "color": TYPE_COLORS["lernblock"],
                "subject_color": b.subject.color if b.subject else None,
                "status": b.status,
                "kind": b.kind,
            }
        )

    for w in db.query(PlannedWorkout).filter(PlannedWorkout.date >= start, PlannedWorkout.date <= end).all():
        s = datetime.combine(w.date, parse_hhmm(w.start_time))
        items.append(
            {
                "id": f"pw-{w.id}",
                "source_id": w.id,
                "type": "training",
                "title": w.title,
                "subtitle": "Geplant" + (" · erledigt" if w.done else ""),
                "start": s,
                "end": s + timedelta(minutes=w.duration_min),
                "all_day": False,
                "color": TYPE_COLORS["training"],
                "status": "erledigt" if w.done else "geplant",
            }
        )

    if include_activities:
        for a in db.query(Activity).filter(Activity.date >= start, Activity.date <= end).all():
            dist = f" · {a.distance_m / 1000:.1f} km".replace(".", ",") if a.distance_m else ""
            items.append(
                {
                    "id": f"act-{a.id}",
                    "source_id": a.id,
                    "type": "training",
                    "title": a.name or activity_label(a.type),
                    "subtitle": f"{activity_label(a.type)}{dist} · absolviert",
                    "start": a.start_time,
                    "end": a.start_time + timedelta(seconds=a.duration_s or 0),
                    "all_day": False,
                    "color": TYPE_COLORS["training"],
                    "status": "erledigt",
                }
            )

    for s in (
        db.query(Subject)
        .filter(Subject.exam_date.isnot(None), Subject.exam_date >= start, Subject.exam_date <= end)
        .all()
    ):
        if s.exam_time:
            st = datetime.combine(s.exam_date, parse_hhmm(s.exam_time))
            en, all_day = st + timedelta(hours=2), False
        else:
            st, en, all_day = datetime.combine(s.exam_date, time.min), datetime.combine(s.exam_date, time.max), True
        items.append(
            {
                "id": f"ex-{s.id}",
                "source_id": s.id,
                "type": "pruefung",
                "title": f"Prüfung: {s.name}",
                "subtitle": s.exam_location,
                "start": st,
                "end": en,
                "all_day": all_day,
                "color": TYPE_COLORS["pruefung"],
                "subject_color": s.color,
            }
        )

    items.sort(key=lambda x: (x["start"], not x["all_day"]))
    return items


def serialize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        d = dict(it)
        d["start"] = it["start"].isoformat()
        d["end"] = it["end"].isoformat()
        d["type_label"] = TYPE_LABELS.get(it["type"], it["type"])
        out.append(d)
    return out
