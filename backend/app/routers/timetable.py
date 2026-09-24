"""Stundenplan: Vorlesungen/Übungen, Semesterzeitraum, freie Zeitfenster."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import TimetableEntry
from ..services import agenda, google_calendar, study_service
from ..services.study_planner import Busy, PlannerConfig, free_intervals
from ..utils import get_or_404, to_dict

router = APIRouter(prefix="/api/timetable", tags=["Stundenplan"])

TIME = r"^\d{2}:\d{2}$"


class EntryIn(BaseModel):
    title: str
    kind: str = "Vorlesung"
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=TIME)
    end_time: str = Field(pattern=TIME)
    room: str = ""
    lecturer: str = ""
    subject_id: int | None = None
    interval_weeks: int = Field(default=1, ge=1, le=4)
    valid_from: Date | None = None
    valid_until: Date | None = None
    color: str | None = None


class EntryPatch(BaseModel):
    title: str | None = None
    kind: str | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: str | None = Field(default=None, pattern=TIME)
    end_time: str | None = Field(default=None, pattern=TIME)
    room: str | None = None
    lecturer: str | None = None
    subject_id: int | None = None
    interval_weeks: int | None = Field(default=None, ge=1, le=4)
    valid_from: Date | None = None
    valid_until: Date | None = None
    color: str | None = None


class SemesterIn(BaseModel):
    name: str = "Semester"
    start: Date | None = None
    end: Date | None = None


def serialize(e: TimetableEntry) -> dict[str, Any]:
    d = to_dict(e)
    d["subject"] = e.subject.name if e.subject else None
    d["subject_color"] = e.subject.color if e.subject else None
    return d


def weekly_free_slots(db: Session, entries: list[TimetableEntry]) -> list[dict[str, Any]]:
    """Freie Zeitfenster je Wochentag innerhalb des Lernfensters (nur wöchentliche Termine blockieren)."""
    study = settings_store.get(db, "study")
    cfg = PlannerConfig(
        day_start=agenda.parse_hhmm(study["day_start"]),
        day_end=agenda.parse_hhmm(study["day_end"]),
        min_block_minutes=45,
        review_minutes=45,
    )
    ref_monday = date(2024, 1, 1)  # beliebige Referenzwoche
    slots = []
    for wd in range(7):
        day = ref_monday + timedelta(days=wd)
        busy = [
            Busy(
                datetime.combine(day, agenda.parse_hhmm(e.start_time)),
                datetime.combine(day, agenda.parse_hhmm(e.end_time)),
            )
            for e in entries
            if e.weekday == wd
        ]
        for s, t in free_intervals(day, busy, cfg):
            slots.append(
                {
                    "weekday": wd,
                    "start_time": s.strftime("%H:%M"),
                    "end_time": t.strftime("%H:%M"),
                    "minutes": int((t - s).total_seconds() // 60),
                }
            )
    return slots


def _after_change(db: Session) -> None:
    study_service.replan(db)
    google_calendar.push_if_enabled(db)


@router.get("")
def timetable(db: Session = Depends(get_db)) -> dict[str, Any]:
    entries = db.query(TimetableEntry).order_by(TimetableEntry.weekday, TimetableEntry.start_time).all()
    semester = settings_store.get(db, "semester") or {}
    today = date.today()
    week_no = None
    if semester.get("start"):
        start = date.fromisoformat(semester["start"])
        week_no = (today - (start - timedelta(days=start.weekday()))).days // 7 + 1
    total_minutes = sum(
        (datetime.combine(today, agenda.parse_hhmm(e.end_time)) - datetime.combine(today, agenda.parse_hhmm(e.start_time))).seconds // 60
        / max(1, e.interval_weeks)
        for e in entries
    )
    return {
        "entries": [serialize(e) for e in entries],
        "semester": semester,
        "semester_week": week_no,
        "free_slots": weekly_free_slots(db, entries),
        "study_window": {k: settings_store.get(db, "study")[k] for k in ("day_start", "day_end")},
        "hours_per_week": round(total_minutes / 60, 1),
    }


@router.post("/entries")
def create_entry(payload: EntryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = TimetableEntry(**payload.model_dump())
    db.add(e)
    db.commit()
    _after_change(db)
    return serialize(e)


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: int, payload: EntryPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = get_or_404(db, TimetableEntry, entry_id, "Stundenplan-Eintrag")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    _after_change(db)
    return serialize(e)


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = get_or_404(db, TimetableEntry, entry_id, "Stundenplan-Eintrag")
    db.delete(e)
    db.commit()
    _after_change(db)
    return {"ok": True}


@router.put("/semester")
def set_semester(payload: SemesterIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings_store.set_value(
        db,
        "semester",
        {
            "name": payload.name,
            "start": payload.start.isoformat() if payload.start else None,
            "end": payload.end.isoformat() if payload.end else None,
        },
    )
    _after_change(db)
    return settings_store.get(db, "semester")
