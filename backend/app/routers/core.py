"""Heute-Übersicht, Einstellungen, Beispieldaten und Export."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import config, models, seed, settings_store
from ..database import get_db
from ..models import (
    DailyMetrics,
    Habit,
    HabitLog,
    Meal,
    SleepRecord,
    StudyBlock,
    Subject,
    Todo,
)
from ..services import agenda, recovery
from ..services.garmin_sync import manager as garmin_manager
from ..services.habits_logic import current_streak
from ..services.study_service import serialize_block
from ..utils import WEEKDAYS_DE, MONTHS_DE, to_dict

router = APIRouter(prefix="/api", tags=["Kern"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "time": datetime.now().isoformat()}


def _greeting(now: datetime, name: str) -> str:
    h = now.hour
    if h < 11:
        word = "Guten Morgen"
    elif h < 17:
        word = "Hallo"
    elif h < 22:
        word = "Guten Abend"
    else:
        word = "Gute Nacht"
    return f"{word}, {name}"


def todo_sort_key(t: Todo, today: date):
    prio = {"hoch": 0, "mittel": 1, "niedrig": 2}.get(t.priority, 1)
    due = t.due_date or date.max
    return (0 if t.due_date and t.due_date <= today else 1, prio, due)


def nutrition_day(db: Session, day: date) -> dict[str, Any]:
    meals = db.query(Meal).filter(Meal.date == day).all()
    s = settings_store.get_all(db)
    metrics = db.get(DailyMetrics, day)
    intake = sum(m.kcal for m in meals)
    burned = metrics.calories_total if metrics and metrics.calories_total else None
    return {
        "intake": round(intake),
        "protein": round(sum(m.protein for m in meals)),
        "carbs": round(sum(m.carbs for m in meals)),
        "fat": round(sum(m.fat for m in meals)),
        "goal": s["kcal_goal"],
        "protein_goal": s["protein_goal"],
        "carbs_goal": s["carbs_goal"],
        "fat_goal": s["fat_goal"],
        "burned": round(burned) if burned else None,
        "balance": round(intake - burned) if burned else None,
        "meals": len(meals),
    }


@router.get("/today")
def today_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    now = datetime.now()
    today = now.date()
    s = settings_store.get_all(db)

    sleep = db.get(SleepRecord, today)
    metrics = db.get(DailyMetrics, today)

    items = agenda.serialize(agenda.agenda(db, today, today, include_activities=True))

    upcoming_blocks = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end >= now)
        .order_by(StudyBlock.start)
        .limit(5)
        .all()
    )

    open_todos = db.query(Todo).filter(Todo.done.is_(False)).all()
    open_todos.sort(key=lambda t: todo_sort_key(t, today))

    habits = db.query(Habit).filter(Habit.active.is_(True)).order_by(Habit.sort, Habit.id).all()
    since = today - timedelta(days=400)
    logs = db.query(HabitLog).filter(HabitLog.date >= since).all()
    by_habit: dict[int, set[date]] = {}
    for log in logs:
        by_habit.setdefault(log.habit_id, set()).add(log.date)

    next_exam = (
        db.query(Subject)
        .filter(Subject.exam_date.isnot(None), Subject.exam_date >= today)
        .order_by(Subject.exam_date)
        .first()
    )

    return {
        "date": today.isoformat(),
        "date_label": f"{WEEKDAYS_DE[today.weekday()]}, {today.day}. {MONTHS_DE[today.month - 1]} {today.year}",
        "greeting": _greeting(now, s["profile_name"]),
        "traffic_light": recovery.traffic_light_for(db, today),
        "sleep": {
            "score": sleep.score,
            "duration_h": round(sleep.duration_s / 3600, 2),
            "deep_h": round(sleep.deep_s / 3600, 2),
            "rem_h": round(sleep.rem_s / 3600, 2),
            "start": sleep.sleep_start.isoformat() if sleep.sleep_start else None,
            "end": sleep.sleep_end.isoformat() if sleep.sleep_end else None,
            "goal_h": s["sleep_goal_hours"],
        }
        if sleep
        else None,
        "metrics": {
            "body_battery_wake": metrics.body_battery_wake,
            "body_battery_high": metrics.body_battery_high,
            "body_battery_low": metrics.body_battery_low,
            "steps": metrics.steps,
            "step_goal": metrics.step_goal,
            "resting_hr": metrics.resting_hr,
            "hrv": metrics.hrv_last_night,
            "hrv_status": metrics.hrv_status,
            "stress": metrics.stress_avg,
            "readiness": metrics.training_readiness,
        }
        if metrics
        else None,
        "agenda": items,
        "study_blocks": [serialize_block(b) for b in upcoming_blocks],
        "todos": [
            {
                **to_dict(t),
                "overdue": bool(t.due_date and t.due_date < today),
                "subject": t.subject.short if t.subject else None,
            }
            for t in open_todos[:7]
        ],
        "todo_count": len(open_todos),
        "habits": [
            {
                "id": h.id,
                "name": h.name,
                "emoji": h.emoji,
                "done": today in by_habit.get(h.id, set()),
                "streak": current_streak(by_habit.get(h.id, set()), today),
            }
            for h in habits
        ],
        "nutrition": nutrition_day(db, today),
        "next_exam": {
            "subject": next_exam.name,
            "date": next_exam.exam_date.isoformat(),
            "days_left": (next_exam.exam_date - today).days,
            "color": next_exam.color,
        }
        if next_exam
        else None,
        "garmin": garmin_manager.status(),
        "demo_active": bool(s.get("demo_active")),
    }


# ---------------------------------------------------------------- Einstellungen

HIDDEN_SETTINGS = {"demo_seeded", "ics_calendars"}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    values = settings_store.get_all(db)
    return {k: v for k, v in values.items() if k not in HIDDEN_SETTINGS}


@router.put("/settings")
def put_settings(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    allowed = {k: v for k, v in payload.items() if k in settings_store.DEFAULT_SETTINGS and k not in HIDDEN_SETTINGS}
    if "study" in allowed:
        allowed["study"] = validate_study(allowed["study"])
    values = settings_store.update_many(db, allowed)
    if {"study", "semester"} & set(allowed):
        from ..services import google_calendar, study_service

        study_service.replan(db)
        google_calendar.push_if_enabled(db)
    return {k: v for k, v in values.items() if k not in HIDDEN_SETTINGS}


def validate_study(study: dict[str, Any]) -> dict[str, Any]:
    """Prüft die Lernplan-Regeln, damit der Planer nicht mit unsinnigen Werten läuft."""
    from fastapi import HTTPException

    from ..services.agenda import parse_hhmm

    merged = dict(settings_store.DEFAULT_SETTINGS["study"])
    merged.update(study or {})
    try:
        if parse_hhmm(merged["day_start"]) >= parse_hhmm(merged["day_end"]):
            raise ValueError("Das Lernfenster muss vor seinem Ende beginnen.")
        for key, lo, hi in (
            ("max_minutes_per_day", 30, 900),
            ("block_minutes", 20, 240),
            ("min_block_minutes", 15, 240),
            ("break_minutes", 0, 120),
            ("buffer_days", 0, 14),
            ("review_minutes", 10, 180),
            ("event_padding_minutes", 0, 120),
            ("workout_padding_minutes", 0, 180),
            ("max_blocks_per_subject_per_day", 1, 10),
        ):
            merged[key] = int(merged[key])
            if not lo <= merged[key] <= hi:
                raise ValueError(f"„{key}“ muss zwischen {lo} und {hi} liegen.")
        merged["review_intervals"] = sorted({int(x) for x in merged["review_intervals"] if int(x) > 0})
        merged["weekdays"] = sorted({int(x) for x in merged["weekdays"] if 0 <= int(x) <= 6})
        if not merged["weekdays"]:
            raise ValueError("Mindestens ein Lerntag muss ausgewählt sein.")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Lernplan-Regeln ungültig: {exc}") from exc
    return merged


@router.get("/status")
def connection_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..services import google_calendar

    return {
        "garmin": garmin_manager.status(),
        "google": google_calendar.status(db),
        "claude": {"configured": bool(config.ANTHROPIC_API_KEY), "model": config.CLAUDE_MODEL},
        "demo_active": bool(settings_store.get(db, "demo_active", False)),
    }


# ---------------------------------------------------------------- Beispieldaten & Export


@router.delete("/demo")
def delete_demo(db: Session = Depends(get_db)) -> dict[str, Any]:
    seed.remove_demo_data(db)
    return {"ok": True}


@router.post("/demo")
def restore_demo(db: Session = Depends(get_db)) -> dict[str, Any]:
    seed.remove_demo_data(db)
    seed.seed_demo_data(db)
    return {"ok": True}


EXPORT_MODELS = [
    models.Activity, models.DailyMetrics, models.SleepRecord, models.PlannedWorkout,
    models.Subject, models.Topic, models.StudyBlock, models.TimetableEntry, models.CalendarEvent,
    models.FocusSession, models.Meal, models.Habit, models.HabitLog, models.Todo, models.JournalEntry,
    models.Transaction, models.StockPosition, models.NewsFeed, models.ChatMessage, models.Setting,
]


@router.get("/export")
def export_data(format: str = "json", db: Session = Depends(get_db)):
    data = {m.__tablename__: [to_dict(row) for row in db.query(m).all()] for m in EXPORT_MODELS}
    stamp = datetime.now().strftime("%Y-%m-%d")
    if format == "csv":
        import csv

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for table, rows in data.items():
                text = io.StringIO()
                if rows:
                    writer = csv.DictWriter(text, fieldnames=list(rows[0].keys()), delimiter=";")
                    writer.writeheader()
                    for r in rows:
                        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in r.items()})
                zf.writestr(f"{table}.csv", "﻿" + text.getvalue())
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="lifeos-export-{stamp}.zip"'},
        )
    payload = json.dumps({"exported_at": datetime.now().isoformat(), "data": data}, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="lifeos-export-{stamp}.json"'},
    )
