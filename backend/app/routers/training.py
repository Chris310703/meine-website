"""Trainingsplan: Wochenplan mit Übungen, Trainingstagebuch (Gewichte, Wiederholungen, Notizen), Fortschritt."""

from __future__ import annotations

from datetime import date, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PlanExercise, TrainingSession, WorkoutLog, WorkoutSet
from ..services import recovery, training
from ..utils import WEEKDAYS_DE, get_or_404

router = APIRouter(prefix="/api/training", tags=["Trainingsplan"])

KIND_PATTERN = r"^(kraft|praevention|fussball|handball|lauf|ruhe|sonstiges)$"


def serialize_exercise(ex: PlanExercise, with_last: bool = False, db: Session | None = None) -> dict[str, Any]:
    top, timed = training.rep_target(ex.reps)
    d = {
        "id": ex.id,
        "session_id": ex.session_id,
        "order_index": ex.order_index,
        "name": ex.name,
        "sets": ex.sets,
        "reps": ex.reps,
        "rep_target": top,
        "timed": timed,
        "rest_seconds": ex.rest_seconds,
        "increment_kg": ex.increment_kg,
        "notes": ex.notes,
        "alternative": ex.alternative,
    }
    if with_last and db is not None:
        last = training.last_performance(db, ex.name)
        d["last"] = last
        d["suggestion"] = training.suggestion(ex, last)
    return d


def serialize_session(s: TrainingSession, db: Session, with_last: bool = False) -> dict[str, Any]:
    last_log = (
        db.query(WorkoutLog).filter(WorkoutLog.session_id == s.id).order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc()).first()
    )
    return {
        "id": s.id,
        "weekday": s.weekday,
        "weekday_label": WEEKDAYS_DE[s.weekday],
        "order_index": s.order_index,
        "kind": s.kind,
        "kind_label": training.KIND_LABELS.get(s.kind, s.kind),
        "title": s.title,
        "notes": s.notes,
        "duration_min": s.duration_min,
        "exercises": [serialize_exercise(e, with_last, db) for e in s.exercises],
        "last_log": {"id": last_log.id, "date": last_log.date.isoformat(), "rating": last_log.rating} if last_log else None,
    }


def serialize_log(log: WorkoutLog) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for st in log.sets:
        g = groups.setdefault(st.exercise_name, {"name": st.exercise_name, "exercise_id": st.exercise_id, "sets": []})
        g["sets"].append({"id": st.id, "set_number": st.set_number, "weight_kg": st.weight_kg, "reps": st.reps, "done": st.done})
    volume = sum((st.weight_kg or 0) * (st.reps or 0) for st in log.sets if st.done)
    return {
        "id": log.id,
        "session_id": log.session_id,
        "date": log.date.isoformat(),
        "weekday_label": WEEKDAYS_DE[log.date.weekday()],
        "title": log.title,
        "kind": log.kind,
        "kind_label": training.KIND_LABELS.get(log.kind, log.kind),
        "notes": log.notes,
        "rating": log.rating,
        "duration_min": log.duration_min,
        "exercises": list(groups.values()),
        "sets_done": sum(1 for st in log.sets if st.done),
        "volume_kg": round(volume),
    }


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ---------------------------------------------------------------- Plan


@router.get("/plan")
def plan(db: Session = Depends(get_db)) -> dict[str, Any]:
    training.ensure_plan(db)
    today = date.today()
    sessions = db.query(TrainingSession).order_by(TrainingSession.weekday, TrainingSession.order_index, TrainingSession.id).all()
    week_start = _week_start(today)
    week_logs = db.query(WorkoutLog).filter(WorkoutLog.date >= week_start, WorkoutLog.date < week_start + timedelta(days=7)).all()
    done_ids = {(log.session_id, log.date.weekday()) for log in week_logs}
    days = []
    for wd in range(7):
        items = []
        for s in sessions:
            if s.weekday != wd:
                continue
            d = serialize_session(s, db)
            d["done_this_week"] = (s.id, wd) in done_ids
            items.append(d)
        days.append({"weekday": wd, "label": WEEKDAYS_DE[wd], "date": (week_start + timedelta(days=wd)).isoformat(), "sessions": items})
    try:
        light = recovery.traffic_light_for(db, today)
    except Exception:  # pragma: no cover – Ampel ist nur ein Zusatz
        light = None
    strength = [s for s in sessions if s.kind in ("kraft", "praevention")]
    return {
        "today_weekday": today.weekday(),
        "days": days,
        "guide": training.GUIDE,
        "kinds": training.KIND_LABELS,
        "traffic_light": light,
        "week": {
            "planned_strength": len(strength),
            "done_strength": sum(1 for log in week_logs if log.kind in ("kraft", "praevention")),
            "logs": len(week_logs),
        },
    }


@router.post("/plan/reset")
def reset_plan(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Stellt den vorgeschlagenen Standardplan wieder her (dein Trainingstagebuch bleibt erhalten)."""
    training.create_default_plan(db)
    return {"ok": True}


class SessionIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    kind: str = Field(default="kraft", pattern=KIND_PATTERN)
    title: str = Field(min_length=1, max_length=150)
    notes: str = ""
    duration_min: int | None = Field(default=None, ge=0, le=600)


class SessionPatch(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    kind: str | None = Field(default=None, pattern=KIND_PATTERN)
    title: str | None = Field(default=None, min_length=1, max_length=150)
    notes: str | None = None
    duration_min: int | None = Field(default=None, ge=0, le=600)


@router.post("/sessions")
def create_session(payload: SessionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    order = db.query(func.max(TrainingSession.order_index)).filter(TrainingSession.weekday == payload.weekday).scalar()
    s = TrainingSession(**payload.model_dump(), order_index=(order + 1) if order is not None else 0)
    db.add(s)
    db.commit()
    return serialize_session(s, db)


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Einheit mit letzter Leistung und Vorschlag je Übung – Grundlage zum Eintragen eines Trainings."""
    s = get_or_404(db, TrainingSession, session_id, "Einheit")
    return serialize_session(s, db, with_last=True)


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, TrainingSession, session_id, "Einheit")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return serialize_session(s, db)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, TrainingSession, session_id, "Einheit")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Übungen


class ExerciseIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    sets: int = Field(default=3, ge=1, le=10)
    reps: str = Field(default="8–12", min_length=1, max_length=30)
    rest_seconds: int = Field(default=90, ge=0, le=600)
    increment_kg: float = Field(default=2.5, ge=0, le=20)
    notes: str = ""
    alternative: str = Field(default="", max_length=250)


class ExercisePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    sets: int | None = Field(default=None, ge=1, le=10)
    reps: str | None = Field(default=None, min_length=1, max_length=30)
    rest_seconds: int | None = Field(default=None, ge=0, le=600)
    increment_kg: float | None = Field(default=None, ge=0, le=20)
    notes: str | None = None
    alternative: str | None = Field(default=None, max_length=250)


@router.post("/sessions/{session_id}/exercises")
def add_exercise(session_id: int, payload: ExerciseIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, TrainingSession, session_id, "Einheit")
    ex = PlanExercise(session_id=s.id, order_index=len(s.exercises), **payload.model_dump())
    db.add(ex)
    db.commit()
    return serialize_exercise(ex)


@router.patch("/exercises/{exercise_id}")
def update_exercise(exercise_id: int, payload: ExercisePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    ex = get_or_404(db, PlanExercise, exercise_id, "Übung")
    data = payload.model_dump(exclude_unset=True)
    old_name = ex.name
    for k, v in data.items():
        setattr(ex, k, v)
    # Umbenennen: bisherige Einträge mitnehmen, damit Verlauf und Vorschläge erhalten bleiben
    if "name" in data and data["name"] != old_name:
        db.query(WorkoutSet).filter(WorkoutSet.exercise_id == ex.id).update({WorkoutSet.exercise_name: data["name"]})
    db.commit()
    return serialize_exercise(ex)


@router.delete("/exercises/{exercise_id}")
def delete_exercise(exercise_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    ex = get_or_404(db, PlanExercise, exercise_id, "Übung")
    db.delete(ex)
    db.commit()
    return {"ok": True}


class ReorderIn(BaseModel):
    exercise_ids: list[int]


@router.post("/sessions/{session_id}/reorder")
def reorder(session_id: int, payload: ReorderIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, TrainingSession, session_id, "Einheit")
    for idx, eid in enumerate(payload.exercise_ids):
        ex = db.get(PlanExercise, eid)
        if ex and ex.session_id == session_id:
            ex.order_index = idx
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Trainingstagebuch


class SetIn(BaseModel):
    exercise_id: int | None = None
    exercise_name: str = Field(min_length=1, max_length=150)
    set_number: int = Field(default=1, ge=1, le=30)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    reps: int | None = Field(default=None, ge=0, le=1000)
    done: bool = True


class LogIn(BaseModel):
    session_id: int | None = None
    date: Date
    title: str = Field(default="", max_length=150)
    kind: str = Field(default="kraft", pattern=KIND_PATTERN)
    notes: str = Field(default="", max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    duration_min: int | None = Field(default=None, ge=0, le=600)
    sets: list[SetIn] = []


def _apply_log(db: Session, log: WorkoutLog, payload: LogIn) -> None:
    session = db.get(TrainingSession, payload.session_id) if payload.session_id else None
    log.session_id = session.id if session else None
    log.date = payload.date
    log.title = payload.title.strip() or (session.title if session else "Training")
    log.kind = payload.kind
    log.notes = payload.notes.strip()
    log.rating = payload.rating
    log.duration_min = payload.duration_min
    log.sets.clear()
    for st in payload.sets:
        # Leere Sätze (weder Gewicht noch Wiederholungen) nicht speichern
        if st.weight_kg is None and st.reps is None:
            continue
        log.sets.append(
            WorkoutSet(
                exercise_id=st.exercise_id,
                exercise_name=st.exercise_name.strip(),
                set_number=st.set_number,
                weight_kg=st.weight_kg,
                reps=st.reps,
                done=st.done,
            )
        )


@router.get("/logs")
def logs(limit: int = 30, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(WorkoutLog).order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc()).limit(max(1, min(limit, 200))).all()
    return [serialize_log(r) for r in rows]


@router.get("/logs/{log_id}")
def get_log(log_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return serialize_log(get_or_404(db, WorkoutLog, log_id, "Training"))


@router.post("/logs")
def create_log(payload: LogIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    log = WorkoutLog(date=payload.date, title="")
    db.add(log)
    _apply_log(db, log, payload)
    db.commit()
    return serialize_log(log)


@router.put("/logs/{log_id}")
def update_log(log_id: int, payload: LogIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    log = get_or_404(db, WorkoutLog, log_id, "Training")
    _apply_log(db, log, payload)
    db.commit()
    return serialize_log(log)


@router.delete("/logs/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    log = get_or_404(db, WorkoutLog, log_id, "Training")
    db.delete(log)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Fortschritt


@router.get("/exercises")
def exercise_names(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Alle Übungen, zu denen es Einträge gibt – für die Fortschritts-Auswahl."""
    rows = (
        db.query(WorkoutSet.exercise_name, func.count(func.distinct(WorkoutSet.log_id)), func.max(WorkoutLog.date))
        .join(WorkoutLog, WorkoutSet.log_id == WorkoutLog.id)
        .group_by(WorkoutSet.exercise_name)
        .order_by(func.max(WorkoutLog.date).desc())
        .all()
    )
    return [{"name": n, "sessions": c, "last_date": d.isoformat() if d else None} for n, c, d in rows]


@router.get("/progress")
def progress(exercise: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    points = training.exercise_progress(db, exercise)
    if not points:
        raise HTTPException(status_code=404, detail="Zu dieser Übung gibt es noch keine Einträge.")
    weights = [p["best_weight"] for p in points if p["best_weight"] is not None]
    return {
        "exercise": exercise,
        "points": points,
        "best_weight": max(weights) if weights else None,
        "first_weight": weights[0] if weights else None,
        "best_e1rm": max((p["e1rm"] for p in points if p["e1rm"]), default=None),
    }
