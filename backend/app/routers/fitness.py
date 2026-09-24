"""Fitness: Aktivitäten, Umfang, HF-Zonen, Zone-2-Pace, VO2max, Wochenziele, geplante Trainings."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import Activity, DailyMetrics, PlannedWorkout
from ..services import agenda, study_service
from ..services.fitness_stats import (
    RunSample,
    category,
    week_key,
    z2_pace_trend,
    zone_bounds,
)
from ..services import google_calendar
from ..utils import MONTHS_DE, add_months, get_or_404, month_start, to_dict

router = APIRouter(prefix="/api/fitness", tags=["Fitness"])


def serialize_activity(a: Activity) -> dict[str, Any]:
    d = to_dict(a)
    d["category"] = category(a.type)
    d["type_label"] = agenda.activity_label(a.type)
    d["pace"] = round(1000 / a.avg_speed / 60, 3) if a.avg_speed and category(a.type) == "laufen" else None
    d["speed_kmh"] = round(a.avg_speed * 3.6, 1) if a.avg_speed else None
    return d


@router.get("/activities")
def activities(days: int = 90, cat: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    since = date.today() - timedelta(days=days)
    rows = db.query(Activity).filter(Activity.date >= since).order_by(Activity.start_time.desc()).all()
    out = [serialize_activity(a) for a in rows]
    if cat:
        out = [a for a in out if a["category"] == cat]
    return out


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    s = settings_store.get_all(db)
    today = date.today()
    since = today - timedelta(days=370)
    acts = db.query(Activity).filter(Activity.date >= since).all()

    # Wochenumfang (letzte 12 Wochen)
    this_week = week_key(today)
    weeks = [this_week - timedelta(weeks=i) for i in range(11, -1, -1)]
    week_data = {w: {"km": 0.0, "hours": 0.0, "sessions": 0, "load": 0.0, "run_km": 0.0} for w in weeks}
    # Monatsumfang (letzte 12 Monate)
    months = [add_months(month_start(today), -i) for i in range(11, -1, -1)]
    month_data = {m: {"km": 0.0, "hours": 0.0, "sessions": 0, "load": 0.0, "run_km": 0.0} for m in months}

    for a in acts:
        for bucket in (week_data.get(week_key(a.date)), month_data.get(month_start(a.date))):
            if bucket is None:
                continue
            bucket["km"] += (a.distance_m or 0) / 1000
            bucket["hours"] += (a.duration_s or 0) / 3600
            bucket["sessions"] += 1
            bucket["load"] += a.training_load or 0
            if category(a.type) == "laufen":
                bucket["run_km"] += (a.distance_m or 0) / 1000

    def rows(data, label_fn):
        return [
            {
                "start": k.isoformat(),
                "label": label_fn(k),
                "km": round(v["km"], 1),
                "run_km": round(v["run_km"], 1),
                "hours": round(v["hours"], 2),
                "sessions": v["sessions"],
                "load": round(v["load"]),
            }
            for k, v in data.items()
        ]

    weekly = rows(week_data, lambda w: f"KW {w.isocalendar()[1]}")
    monthly = rows(month_data, lambda m: f"{MONTHS_DE[m.month - 1][:3]} {str(m.year)[2:]}")

    # Zeit in HF-Zonen (letzte 28 Tage + Vorperiode)
    def zone_totals(start: date, end: date) -> list[float]:
        totals = [0.0] * 5
        for a in acts:
            if start <= a.date <= end:
                for z in range(5):
                    totals[z] += getattr(a, f"z{z + 1}_s") or 0
        return totals

    cur = zone_totals(today - timedelta(days=27), today)
    prev = zone_totals(today - timedelta(days=55), today - timedelta(days=28))
    bounds = zone_bounds(float(s["max_hr"]), [float(x) for x in s["hr_zone_limits"]])
    zones = [
        {
            "zone": f"Z{i + 1}",
            "range": f"{bounds[i][0]}–{bounds[i][1]} bpm",
            "minutes": round(cur[i] / 60),
            "prev_minutes": round(prev[i] / 60),
            "share": round(cur[i] / sum(cur) * 100) if sum(cur) else 0,
        }
        for i in range(5)
    ]

    # Zone-2-Pace bei gleicher Herzfrequenz
    z2_low, z2_high = bounds[1]
    samples = []
    for a in acts:
        if category(a.type) != "laufen" or not a.avg_speed or not a.avg_hr or a.date < today - timedelta(days=180):
            continue
        total_z = sum(getattr(a, f"z{z}_s") or 0 for z in range(1, 6))
        samples.append(RunSample(a.date, a.avg_speed, a.avg_hr, (a.z2_s or 0) / total_z if total_z else 0, a.duration_s))
    z2 = z2_pace_trend(samples, z2_low, z2_high, float(s["z2_reference_hr"]))
    z2["zone_range"] = f"{z2_low}–{z2_high} bpm"

    # VO2max-Verlauf
    vo2 = [
        {"date": m.date.isoformat(), "vo2max": m.vo2max}
        for m in db.query(DailyMetrics)
        .filter(DailyMetrics.vo2max.isnot(None), DailyMetrics.date >= today - timedelta(days=365))
        .order_by(DailyMetrics.date)
        .all()
    ]
    if not vo2:
        vo2 = [
            {"date": a.date.isoformat(), "vo2max": a.vo2max}
            for a in sorted(acts, key=lambda x: x.date)
            if a.vo2max
        ]

    # Wochenziele
    wk = week_data[this_week]
    goals = [
        {"key": "run_km", "label": "Laufkilometer", "value": round(wk["run_km"], 1), "goal": s["weekly_run_km_goal"], "unit": "km"},
        {"key": "hours", "label": "Trainingszeit", "value": round(wk["hours"], 1), "goal": s["weekly_training_hours_goal"], "unit": "h"},
        {"key": "sessions", "label": "Einheiten", "value": wk["sessions"], "goal": s["weekly_sessions_goal"], "unit": ""},
    ]

    last_30 = [a for a in acts if a.date >= today - timedelta(days=29)]
    by_cat: dict[str, dict[str, float]] = defaultdict(lambda: {"sessions": 0, "hours": 0.0, "km": 0.0})
    for a in last_30:
        c = by_cat[category(a.type)]
        c["sessions"] += 1
        c["hours"] += (a.duration_s or 0) / 3600
        c["km"] += (a.distance_m or 0) / 1000

    return {
        "weekly": weekly,
        "monthly": monthly,
        "zones": zones,
        "z2": z2,
        "vo2max": vo2,
        "goals": goals,
        "categories": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in by_cat.items()},
        "max_hr": s["max_hr"],
    }


# ---------------------------------------------------------------- Geplante Trainings


class WorkoutIn(BaseModel):
    date: Date
    start_time: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    duration_min: int = Field(default=60, ge=5, le=600)
    type: str = "running"
    title: str = "Training"
    notes: str = ""
    done: bool = False


class WorkoutPatch(BaseModel):
    date: Date | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_min: int | None = Field(default=None, ge=5, le=600)
    type: str | None = None
    title: str | None = None
    notes: str | None = None
    done: bool | None = None


def _after_workout_change(db: Session) -> None:
    study_service.replan(db)
    google_calendar.push_if_enabled(db)


@router.get("/planned")
def planned(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    since = date.today() - timedelta(days=7)
    rows = db.query(PlannedWorkout).filter(PlannedWorkout.date >= since).order_by(PlannedWorkout.date, PlannedWorkout.start_time).all()
    return [{**to_dict(w), "type_label": agenda.activity_label(w.type), "synced": bool(w.google_event_id)} for w in rows]


@router.post("/planned")
def create_planned(payload: WorkoutIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = PlannedWorkout(**payload.model_dump())
    db.add(w)
    db.commit()
    _after_workout_change(db)
    return to_dict(w)


@router.patch("/planned/{workout_id}")
def update_planned(workout_id: int, payload: WorkoutPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = get_or_404(db, PlannedWorkout, workout_id, "Training")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    db.commit()
    _after_workout_change(db)
    return to_dict(w)


@router.delete("/planned/{workout_id}")
def delete_planned(workout_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = get_or_404(db, PlannedWorkout, workout_id, "Training")
    google_calendar.delete_remote_event(db, w.google_event_id)
    db.delete(w)
    db.commit()
    _after_workout_change(db)
    return {"ok": True}
