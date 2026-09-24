"""Habits (abhaken, Streaks, Heatmap) und Fokus-Timer-Protokoll (Pomodoro)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FocusSession, Habit, HabitLog, StudyBlock, Subject
from ..services import google_calendar, study_service
from ..services.habits_logic import current_streak, longest_streak
from ..utils import get_or_404, to_dict

router = APIRouter(prefix="/api", tags=["Habits"])


class HabitIn(BaseModel):
    name: str = Field(min_length=1)
    emoji: str = "✅"
    active: bool = True


class HabitPatch(BaseModel):
    name: str | None = None
    emoji: str | None = None
    active: bool | None = None
    sort: int | None = None


class ToggleIn(BaseModel):
    date: Date | None = None


@router.get("/habits")
def habits(weeks: int = 26, db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    all_habits = db.query(Habit).order_by(Habit.sort, Habit.id).all()
    since = today - timedelta(days=max(weeks * 7, 400))
    logs = db.query(HabitLog).filter(HabitLog.date >= since).all()
    by_habit: dict[int, set[date]] = defaultdict(set)
    for log in logs:
        by_habit[log.habit_id].add(log.date)

    active = [h for h in all_habits if h.active]
    week_start = today - timedelta(days=today.weekday())
    items = []
    for h in all_habits:
        done = by_habit.get(h.id, set())
        last30 = sum(1 for i in range(30) if today - timedelta(days=i) in done)
        items.append(
            {
                **to_dict(h),
                "done_today": today in done,
                "streak": current_streak(done, today),
                "longest": longest_streak(done),
                "rate_30": round(last30 / 30 * 100),
                "week": [(week_start + timedelta(days=i)) in done for i in range(7)],
            }
        )

    # Heatmap: Anteil erledigter aktiver Habits pro Tag
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    per_day: dict[date, int] = defaultdict(int)
    active_ids = {h.id for h in active}
    for log in logs:
        if log.habit_id in active_ids:
            per_day[log.date] += 1
    heatmap = []
    d = start
    while d <= today:
        heatmap.append({"date": d.isoformat(), "done": per_day.get(d, 0), "total": len(active), "share": round(per_day.get(d, 0) / len(active), 2) if active else 0})
        d += timedelta(days=1)
    return {"habits": items, "heatmap": heatmap, "week_start": week_start.isoformat()}


@router.post("/habits")
def create_habit(payload: HabitIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    h = Habit(**payload.model_dump(), sort=db.query(Habit).count())
    db.add(h)
    db.commit()
    return to_dict(h)


@router.patch("/habits/{habit_id}")
def update_habit(habit_id: int, payload: HabitPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    h = get_or_404(db, Habit, habit_id, "Habit")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    db.commit()
    return to_dict(h)


@router.delete("/habits/{habit_id}")
def delete_habit(habit_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    h = get_or_404(db, Habit, habit_id, "Habit")
    db.delete(h)
    db.commit()
    return {"ok": True}


@router.post("/habits/{habit_id}/toggle")
def toggle_habit(habit_id: int, payload: ToggleIn | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    h = get_or_404(db, Habit, habit_id, "Habit")
    d = (payload.date if payload and payload.date else None) or date.today()
    log = db.query(HabitLog).filter(HabitLog.habit_id == h.id, HabitLog.date == d).one_or_none()
    if log:
        db.delete(log)
        done = False
    else:
        db.add(HabitLog(habit_id=h.id, date=d))
        done = True
    db.commit()
    dates = {x.date for x in db.query(HabitLog).filter(HabitLog.habit_id == h.id).all()}
    return {"done": done, "streak": current_streak(dates, date.today())}


# ---------------------------------------------------------------- Fokus-Timer


class FocusIn(BaseModel):
    start: datetime
    end: datetime
    minutes: float = Field(gt=0, le=600)
    subject_id: int | None = None
    study_block_id: int | None = None
    note: str = ""
    mark_block_done: bool = False


@router.get("/focus")
def focus(days: int = 14, db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())
    sessions = db.query(FocusSession).filter(FocusSession.start >= since).order_by(FocusSession.start.desc()).all()
    per_day = defaultdict(float)
    per_subject: dict[str, float] = defaultdict(float)
    for s in sessions:
        per_day[s.start.date()] += s.minutes
        per_subject[s.subject.name if s.subject else "Ohne Fach"] += s.minutes
    daily = [{"date": (today - timedelta(days=i)).isoformat(), "minutes": round(per_day.get(today - timedelta(days=i), 0))} for i in range(days - 1, -1, -1)]
    now = datetime.now()
    blocks = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end >= now - timedelta(hours=3), StudyBlock.start <= now + timedelta(days=1))
        .order_by(StudyBlock.start)
        .all()
    )
    return {
        "sessions": [
            {**to_dict(s), "subject": s.subject.name if s.subject else None, "subject_color": s.subject.color if s.subject else None}
            for s in sessions[:40]
        ],
        "daily": daily,
        "per_subject": [{"subject": k, "minutes": round(v)} for k, v in sorted(per_subject.items(), key=lambda x: -x[1])],
        "today_minutes": round(per_day.get(today, 0)),
        "today_sessions": sum(1 for s in sessions if s.start.date() == today),
        "subjects": [{"id": s.id, "name": s.name, "color": s.color} for s in db.query(Subject).filter(Subject.active.is_(True)).order_by(Subject.name).all()],
        "blocks": [
            {"id": b.id, "title": b.title, "subject_id": b.subject_id, "start": b.start.isoformat(), "end": b.end.isoformat()}
            for b in blocks
        ],
    }


@router.post("/focus")
def log_focus(payload: FocusIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    subject_id = payload.subject_id
    block = db.get(StudyBlock, payload.study_block_id) if payload.study_block_id else None
    if block and not subject_id:
        subject_id = block.subject_id
    s = FocusSession(
        start=payload.start.replace(tzinfo=None),
        end=payload.end.replace(tzinfo=None),
        minutes=payload.minutes,
        subject_id=subject_id,
        study_block_id=block.id if block else None,
        note=payload.note,
    )
    db.add(s)
    db.commit()
    if block and payload.mark_block_done:
        block.status = "erledigt"
        db.commit()
        if block.topic:
            study_service.update_topic_status(db, block.topic)
            db.commit()
        study_service.replan(db)
        google_calendar.push_if_enabled(db)
    return to_dict(s)


@router.delete("/focus/{session_id}")
def delete_focus(session_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, FocusSession, session_id, "Fokus-Session")
    db.delete(s)
    db.commit()
    return {"ok": True}
