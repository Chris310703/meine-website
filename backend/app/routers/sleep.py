"""Schlaf: Dauer & Phasen pro Nacht, Score-Verlauf, Einschlaf-/Aufwachzeiten, Regelmäßigkeit."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import pstdev
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import SleepRecord
from ..utils import rnd, safe_mean

router = APIRouter(prefix="/api/sleep", tags=["Schlaf"])


def clock_minutes(dt: datetime | None, pivot_hour: int = 12) -> float | None:
    """Uhrzeit → Minuten relativ zu Mitternacht; Abendzeiten negativ (23:30 → −30)."""
    if dt is None:
        return None
    m = dt.hour * 60 + dt.minute
    if dt.hour >= pivot_hour:
        m -= 24 * 60
    return m


def regularity(records: list[SleepRecord]) -> dict[str, Any]:
    beds = [clock_minutes(r.sleep_start) for r in records if r.sleep_start]
    wakes = [clock_minutes(r.sleep_end) for r in records if r.sleep_end]
    if len(beds) < 3 or len(wakes) < 3:
        return {"score": None, "bed_sd": None, "wake_sd": None, "label": "Zu wenige Daten"}
    bed_sd, wake_sd = pstdev(beds), pstdev(wakes)
    score = max(0, min(100, round(100 - (bed_sd + wake_sd) * 0.8)))
    label = "sehr regelmäßig" if score >= 80 else "regelmäßig" if score >= 60 else "schwankend" if score >= 40 else "unregelmäßig"
    return {"score": score, "bed_sd": round(bed_sd), "wake_sd": round(wake_sd), "label": label}


def averages(records: list[SleepRecord]) -> dict[str, Any]:
    if not records:
        return {"nights": 0}
    beds = [clock_minutes(r.sleep_start) for r in records if r.sleep_start]
    wakes = [clock_minutes(r.sleep_end) for r in records if r.sleep_end]
    return {
        "nights": len(records),
        "duration_h": rnd(safe_mean(r.duration_s / 3600 for r in records), 2),
        "deep_h": rnd(safe_mean(r.deep_s / 3600 for r in records), 2),
        "light_h": rnd(safe_mean(r.light_s / 3600 for r in records), 2),
        "rem_h": rnd(safe_mean(r.rem_s / 3600 for r in records), 2),
        "awake_h": rnd(safe_mean(r.awake_s / 3600 for r in records), 2),
        "score": rnd(safe_mean(r.score for r in records), 0),
        "bedtime_min": rnd(safe_mean(beds), 0),
        "waketime_min": rnd(safe_mean(wakes), 0),
    }


@router.get("")
def sleep_overview(days: int = 30, db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    goal = float(settings_store.get(db, "sleep_goal_hours") or 8)
    since = today - timedelta(days=max(days, 60) - 1)
    records = db.query(SleepRecord).filter(SleepRecord.date >= since).order_by(SleepRecord.date).all()
    shown = [r for r in records if r.date >= today - timedelta(days=days - 1)]

    nights = [
        {
            "date": r.date.isoformat(),
            "duration_h": round(r.duration_s / 3600, 2),
            "deep_h": round(r.deep_s / 3600, 2),
            "light_h": round(r.light_s / 3600, 2),
            "rem_h": round(r.rem_s / 3600, 2),
            "awake_h": round(r.awake_s / 3600, 2),
            "score": r.score,
            "qualifier": r.score_qualifier,
            "start": r.sleep_start.isoformat() if r.sleep_start else None,
            "end": r.sleep_end.isoformat() if r.sleep_end else None,
            "bed_min": clock_minutes(r.sleep_start),
            "wake_min": clock_minutes(r.sleep_end),
            "avg_hrv": r.avg_hrv,
            "resting_hr": r.resting_hr,
            "goal_met": r.duration_s / 3600 >= goal,
        }
        for r in shown
    ]
    last7 = [r for r in records if r.date > today - timedelta(days=7)]
    prev7 = [r for r in records if today - timedelta(days=14) < r.date <= today - timedelta(days=7)]
    last30 = [r for r in records if r.date > today - timedelta(days=30)]

    # Durchschnitt je Kalenderwoche (letzte 8 Wochen)
    weekly = []
    monday = today - timedelta(days=today.weekday())
    for i in range(7, -1, -1):
        start = monday - timedelta(weeks=i)
        rs = [r for r in records if start <= r.date < start + timedelta(days=7)]
        if rs:
            weekly.append({"week": f"KW {start.isocalendar()[1]}", "start": start.isoformat(), **averages(rs)})

    return {
        "goal_h": goal,
        "bedtime_target": settings_store.get(db, "bedtime_target"),
        "wake_target": settings_store.get(db, "wake_target"),
        "nights": nights,
        "avg_7": averages(last7),
        "avg_prev_7": averages(prev7),
        "avg_30": averages(last30),
        "weekly": weekly,
        "regularity_14": regularity([r for r in records if r.date > today - timedelta(days=14)]),
        "goal_met_7": sum(1 for r in last7 if r.duration_s / 3600 >= goal),
        "goal_met_30": sum(1 for r in last30 if r.duration_s / 3600 >= goal),
    }
