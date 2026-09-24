"""Journal: Morgen- und Abendeintrag mit Leitfragen und Stimmung (1–5), durchsuchbar."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import JournalEntry
from ..utils import parse_date, to_dict

router = APIRouter(prefix="/api/journal", tags=["Journal"])

KINDS = ("morgen", "abend")


class EntryIn(BaseModel):
    mood: int | None = Field(default=None, ge=1, le=5)
    answers: dict[str, str] = {}
    text: str = ""


def _matches(e: JournalEntry, q: str) -> bool:
    haystack = " ".join([e.text or "", *[f"{k} {v}" for k, v in (e.answers or {}).items()]]).lower()
    return all(word in haystack for word in q.lower().split())


@router.get("")
def list_entries(q: str = "", mood: int | None = None, limit: int = 60, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(JournalEntry).order_by(JournalEntry.date.desc(), JournalEntry.kind.desc()).all()
    if q.strip():
        rows = [e for e in rows if _matches(e, q)]
    if mood:
        rows = [e for e in rows if e.mood == mood]
    today = date.today()
    recent = [e for e in db.query(JournalEntry).filter(JournalEntry.date >= today - timedelta(days=29)).all() if e.mood]
    per_day: dict[date, list[int]] = {}
    for e in recent:
        per_day.setdefault(e.date, []).append(e.mood)
    trend = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "mood": round(sum(per_day[today - timedelta(days=i)]) / len(per_day[today - timedelta(days=i)]), 1) if (today - timedelta(days=i)) in per_day else None,
        }
        for i in range(29, -1, -1)
    ]
    moods = [e.mood for e in recent]
    streak = 0
    dates = {e.date for e in db.query(JournalEntry.date).all()}
    cursor = today if today in dates else today - timedelta(days=1)
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return {
        "entries": [to_dict(e) for e in rows[:limit]],
        "total": len(rows),
        "trend": trend,
        "avg_mood_30": round(sum(moods) / len(moods), 1) if moods else None,
        "streak": streak,
    }


@router.get("/day/{day}")
def day_entries(day: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = parse_date(day)
    entries = {e.kind: to_dict(e) for e in db.query(JournalEntry).filter(JournalEntry.date == d).all()}
    return {
        "date": d.isoformat(),
        "questions": settings_store.get(db, "journal_questions"),
        "morgen": entries.get("morgen"),
        "abend": entries.get("abend"),
    }


@router.put("/day/{day}/{kind}")
def save_entry(day: str, kind: str, payload: EntryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Art muss „morgen“ oder „abend“ sein.")
    d = parse_date(day)
    e = db.query(JournalEntry).filter(JournalEntry.date == d, JournalEntry.kind == kind).one_or_none()
    if e is None:
        e = JournalEntry(date=d, kind=kind)
        db.add(e)
    e.mood = payload.mood
    e.answers = {k: v for k, v in payload.answers.items() if v.strip()}
    e.text = payload.text
    db.commit()
    return to_dict(e)


@router.delete("/day/{day}/{kind}")
def delete_entry(day: str, kind: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = parse_date(day)
    e = db.query(JournalEntry).filter(JournalEntry.date == d, JournalEntry.kind == kind).one_or_none()
    if e:
        db.delete(e)
        db.commit()
    return {"ok": True}
