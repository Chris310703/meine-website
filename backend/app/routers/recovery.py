"""Recovery: Ampel, HRV, Ruhepuls, Body Battery, Stress, Trainingsbelastung, Erholungszeit."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DailyMetrics, SleepRecord
from ..services import recovery
from ..utils import rnd, safe_mean

router = APIRouter(prefix="/api/recovery", tags=["Recovery"])


@router.get("")
def recovery_overview(days: int = 60, db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    since = today - timedelta(days=days - 1)
    metrics = db.query(DailyMetrics).filter(DailyMetrics.date >= since).order_by(DailyMetrics.date).all()
    sleep = {s.date: s for s in db.query(SleepRecord).filter(SleepRecord.date >= since).all()}

    series = []
    for m in metrics:
        series.append(
            {
                "date": m.date.isoformat(),
                "hrv": m.hrv_last_night or (sleep[m.date].avg_hrv if m.date in sleep else None),
                "hrv_weekly": m.hrv_weekly_avg,
                "baseline": [m.hrv_baseline_low, m.hrv_baseline_high] if m.hrv_baseline_low and m.hrv_baseline_high else None,
                "hrv_status": m.hrv_status,
                "rhr": m.resting_hr,
                "bb_high": m.body_battery_high,
                "bb_low": m.body_battery_low,
                "bb_range": [m.body_battery_low, m.body_battery_high] if m.body_battery_low is not None and m.body_battery_high is not None else None,
                "bb_wake": m.body_battery_wake,
                "stress": m.stress_avg,
                "acute": m.acute_load,
                "chronic": m.chronic_load,
                "acwr": m.acwr,
                "readiness": m.training_readiness,
                "recovery_h": m.recovery_time_h,
                "training_status": m.training_status,
            }
        )

    def avg(key: str, start: int, end: int) -> float | None:
        lo, hi = today - timedelta(days=start), today - timedelta(days=end)
        return rnd(safe_mean(s[key] for s in series if lo < date.fromisoformat(s["date"]) <= hi), 1)

    # Ampel-Verlauf der letzten 14 Tage
    history = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        r = recovery.evaluate(recovery.build_inputs(db, d))
        history.append({"date": d.isoformat(), "color": r["color"], "score": r["score"]})

    latest = metrics[-1] if metrics else None
    return {
        "traffic_light": recovery.traffic_light_for(db, today),
        "history": history,
        "series": series,
        "today": {
            "hrv": latest.hrv_last_night if latest else None,
            "hrv_status": latest.hrv_status if latest else None,
            "rhr": latest.resting_hr if latest else None,
            "recovery_h": latest.recovery_time_h if latest else None,
            "readiness": latest.training_readiness if latest else None,
            "training_status": latest.training_status if latest else None,
            "acute": latest.acute_load if latest else None,
            "chronic": latest.chronic_load if latest else None,
            "acwr": latest.acwr if latest else None,
            "bb_wake": latest.body_battery_wake if latest else None,
            "stress": latest.stress_avg if latest else None,
        },
        "trends": {
            "hrv_7": avg("hrv", 7, 0),
            "hrv_prev_7": avg("hrv", 14, 7),
            "rhr_7": avg("rhr", 7, 0),
            "rhr_30": avg("rhr", 30, 0),
            "stress_7": avg("stress", 7, 0),
            "stress_prev_7": avg("stress", 14, 7),
        },
    }
