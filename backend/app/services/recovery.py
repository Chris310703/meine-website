"""Recovery-Ampel: bewertet Erholungswerte und gibt eine Tagesempfehlung.

grün = hart trainieren, gelb = locker, rot = Ruhetag.
Die Bewertung ist eine reine Funktion (`evaluate`), damit sie gut testbar ist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from statistics import mean

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import DailyMetrics, SleepRecord


@dataclass
class RecoveryInputs:
    sleep_score: float | None = None
    sleep_hours: float | None = None
    sleep_goal_hours: float = 8.0
    hrv_last_night: float | None = None
    hrv_weekly_avg: float | None = None
    hrv_baseline_low: float | None = None
    hrv_baseline_high: float | None = None
    hrv_status: str | None = None
    resting_hr: float | None = None
    resting_hr_baseline: float | None = None
    body_battery: float | None = None
    training_readiness: float | None = None
    training_readiness_level: str | None = None
    acwr: float | None = None
    recovery_time_h: float | None = None
    stress_avg: float | None = None


@dataclass
class Factor:
    key: str
    label: str
    score: float
    weight: float
    text: str
    critical: bool = field(default=False)


# Faktoren, die bei sehr schlechtem Wert als „kritisch“ zählen
CRITICAL_KEYS = {"hrv", "rhr", "sleep", "body_battery", "readiness", "load", "recovery_time"}
CRITICAL_THRESHOLD = 35
WEAK_THRESHOLD = 50

HEADLINES = {
    "gruen": ("Grün", "Hart trainieren", "Du bist gut erholt – Intervalle, Tempo oder ein langer Lauf sind heute drin."),
    "gelb": ("Gelb", "Locker trainieren", "Nur lockere Einheit: Zone 2, Technik oder Mobility – keine harten Reize."),
    "rot": ("Rot", "Ruhetag", "Dein Körper braucht Erholung: Spaziergang, Dehnen, viel trinken und früh schlafen."),
    "grau": ("Keine Daten", "Noch keine Daten", "Synchronisiere Garmin, um eine Empfehlung zu erhalten."),
}


def _fmt(value: float, digits: int = 0) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",")


def _hours_text(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h}:{m:02d} h"


def _hrv_factor(i: RecoveryInputs) -> Factor | None:
    status = (i.hrv_status or "").upper()
    value_txt = f"HRV {_fmt(i.hrv_last_night)} ms" if i.hrv_last_night else "HRV"
    base_txt = ""
    if i.hrv_baseline_low and i.hrv_baseline_high:
        base_txt = f" (Normalbereich {_fmt(i.hrv_baseline_low)}–{_fmt(i.hrv_baseline_high)})"
    score: float | None = None
    text = ""
    if status in {"BALANCED", "UNBALANCED", "LOW", "POOR"}:
        score, word = {
            "BALANCED": (85, "ausgeglichen"),
            "UNBALANCED": (55, "unausgeglichen"),
            "LOW": (30, "niedrig"),
            "POOR": (15, "sehr niedrig"),
        }[status]
        text = f"{value_txt} – Status {word}{base_txt}"
    elif i.hrv_last_night and i.hrv_baseline_low and i.hrv_baseline_high:
        if i.hrv_last_night < i.hrv_baseline_low:
            score, word = 35, "unter dem Normalbereich"
        elif i.hrv_last_night > i.hrv_baseline_high:
            score, word = 70, "über dem Normalbereich"
        else:
            score, word = 80, "im Normalbereich"
        text = f"{value_txt} {word}{base_txt}"
    elif i.hrv_last_night and i.hrv_weekly_avg:
        ratio = i.hrv_last_night / i.hrv_weekly_avg
        score = 80 if ratio >= 0.95 else 55 if ratio >= 0.85 else 30
        text = f"{value_txt} ({_fmt(ratio * 100)} % des Wochenschnitts)"
    if score is None:
        return None
    if i.hrv_last_night and i.hrv_weekly_avg and i.hrv_last_night < 0.85 * i.hrv_weekly_avg:
        score = min(score, 40)
        text += " – deutlich unter Wochenschnitt"
    return Factor("hrv", "HRV", score, 3, text)


def _rhr_factor(i: RecoveryInputs) -> Factor | None:
    if i.resting_hr is None:
        return None
    if i.resting_hr_baseline is None:
        return Factor("rhr", "Ruhepuls", 70, 1, f"Ruhepuls {_fmt(i.resting_hr)} bpm (noch keine Vergleichswerte)")
    delta = i.resting_hr - i.resting_hr_baseline
    if delta <= -1:
        score = 95
    elif delta <= 1:
        score = 85
    elif delta <= 3:
        score = 65
    elif delta <= 5:
        score = 45
    else:
        score = 20
    sign = "+" if delta >= 0 else "−"
    text = f"Ruhepuls {_fmt(i.resting_hr)} bpm ({sign}{_fmt(abs(delta))} zum 30-Tage-Schnitt)"
    if delta > 5:
        text += " – deutlich erhöht"
    return Factor("rhr", "Ruhepuls", score, 2, text)


def _sleep_factor(i: RecoveryInputs) -> Factor | None:
    if i.sleep_score is None and i.sleep_hours is None:
        return None
    if i.sleep_score is not None:
        score = float(i.sleep_score)
    else:
        score = min(95.0, (i.sleep_hours or 0) / max(i.sleep_goal_hours, 1) * 90)
    parts = []
    if i.sleep_score is not None:
        parts.append(f"Schlafscore {_fmt(i.sleep_score)}")
    if i.sleep_hours is not None:
        parts.append(_hours_text(i.sleep_hours))
        if i.sleep_hours < 5:
            score = min(score, 25)
        elif i.sleep_hours < 6:
            score = min(score, 40)
    text = ", ".join(parts)
    if i.sleep_hours is not None and i.sleep_hours < 6:
        text += " – zu kurze Nacht"
    return Factor("sleep", "Schlaf", score, 2, text)


def _body_battery_factor(i: RecoveryInputs) -> Factor | None:
    if i.body_battery is None:
        return None
    value = max(0.0, min(100.0, float(i.body_battery)))
    return Factor("body_battery", "Body Battery", value, 2, f"Body Battery {_fmt(value)} am Morgen")


def _readiness_factor(i: RecoveryInputs) -> Factor | None:
    if i.training_readiness is None:
        return None
    level = {
        "PRIME": "optimal",
        "HIGH": "hoch",
        "MODERATE": "moderat",
        "LOW": "niedrig",
        "POOR": "sehr niedrig",
    }.get((i.training_readiness_level or "").upper(), "")
    text = f"Trainingsbereitschaft {_fmt(i.training_readiness)}"
    if level:
        text += f" ({level})"
    return Factor("readiness", "Trainingsbereitschaft", float(i.training_readiness), 3, text)


def _load_factor(i: RecoveryInputs) -> Factor | None:
    if i.acwr is None:
        return None
    r = i.acwr
    if r < 0.8:
        score, text = 80, "Belastung niedrig – Luft nach oben"
    elif r <= 1.3:
        score, text = 85, "Belastung im optimalen Bereich"
    elif r <= 1.5:
        score, text = 50, "Belastung steigt schnell"
    else:
        score, text = 20, "Überlastungsgefahr"
    return Factor("load", "Trainingsbelastung", score, 1.5, f"Akut/chronisch {_fmt(r, 2)} – {text}")


def _recovery_time_factor(i: RecoveryInputs) -> Factor | None:
    if i.recovery_time_h is None:
        return None
    h = i.recovery_time_h
    if h <= 6:
        score = 95
    elif h <= 18:
        score = 75
    elif h <= 30:
        score = 50
    elif h <= 48:
        score = 30
    else:
        score = 15
    text = "Vollständig erholt" if h <= 0 else f"Erholungszeit noch {_fmt(h)} h"
    return Factor("recovery_time", "Erholungszeit", score, 1.5, text)


def _stress_factor(i: RecoveryInputs) -> Factor | None:
    if i.stress_avg is None:
        return None
    s = i.stress_avg
    score = 90 if s <= 25 else 75 if s <= 35 else 50 if s <= 50 else 30
    return Factor("stress", "Stress", score, 1, f"Stress gestern Ø {_fmt(s)}")


def evaluate(inputs: RecoveryInputs) -> dict:
    builders = (
        _readiness_factor,
        _hrv_factor,
        _rhr_factor,
        _sleep_factor,
        _body_battery_factor,
        _load_factor,
        _recovery_time_factor,
        _stress_factor,
    )
    factors = [f for f in (b(inputs) for b in builders) if f is not None]
    for f in factors:
        f.critical = f.key in CRITICAL_KEYS and f.score < CRITICAL_THRESHOLD

    if not factors:
        label, headline, recommendation = HEADLINES["grau"]
        return {
            "color": "grau",
            "label": label,
            "headline": headline,
            "recommendation": recommendation,
            "score": None,
            "reasons": [],
            "factors": [],
        }

    total_weight = sum(f.weight for f in factors)
    score = sum(f.score * f.weight for f in factors) / total_weight
    critical = sum(1 for f in factors if f.critical)
    # Deutlich schwache Einzelwerte (unter 50) verhindern „grün“
    weak = sum(1 for f in factors if f.key in CRITICAL_KEYS and f.score < WEAK_THRESHOLD)

    if critical >= 2 or score < 45:
        color = "rot"
    elif score >= 70 and weak == 0:
        color = "gruen"
    else:
        color = "gelb"

    if color == "gruen":
        ordered = sorted(factors, key=lambda f: (-f.score * f.weight, f.key))
    else:
        ordered = sorted(factors, key=lambda f: (not f.critical, f.score, -f.weight))
    reasons = [f.text for f in ordered[:3]]

    label, headline, recommendation = HEADLINES[color]
    return {
        "color": color,
        "label": label,
        "headline": headline,
        "recommendation": recommendation,
        "score": round(score),
        "reasons": reasons,
        "factors": [asdict(f) for f in factors],
    }


def build_inputs(db: Session, day: date) -> RecoveryInputs:
    metrics = db.get(DailyMetrics, day)
    sleep = db.get(SleepRecord, day)
    yesterday = db.get(DailyMetrics, day - timedelta(days=1))
    history = (
        db.query(DailyMetrics.resting_hr)
        .filter(DailyMetrics.date >= day - timedelta(days=30), DailyMetrics.date < day)
        .all()
    )
    rhr_values = [r[0] for r in history if r[0]]
    inputs = RecoveryInputs(
        sleep_goal_hours=float(settings_store.get(db, "sleep_goal_hours") or 8),
        resting_hr_baseline=round(mean(rhr_values), 1) if len(rhr_values) >= 5 else None,
    )
    if sleep is not None:
        inputs.sleep_score = sleep.score
        inputs.sleep_hours = sleep.duration_s / 3600 if sleep.duration_s else None
    if metrics is not None:
        inputs.hrv_last_night = metrics.hrv_last_night or (sleep.avg_hrv if sleep else None)
        inputs.hrv_weekly_avg = metrics.hrv_weekly_avg
        inputs.hrv_baseline_low = metrics.hrv_baseline_low
        inputs.hrv_baseline_high = metrics.hrv_baseline_high
        inputs.hrv_status = metrics.hrv_status
        inputs.resting_hr = metrics.resting_hr or (sleep.resting_hr if sleep else None)
        inputs.body_battery = metrics.body_battery_wake or metrics.body_battery_high
        inputs.training_readiness = metrics.training_readiness
        inputs.training_readiness_level = metrics.training_readiness_level
        inputs.acwr = metrics.acwr
        inputs.recovery_time_h = metrics.recovery_time_h
    elif sleep is not None:
        inputs.hrv_last_night = sleep.avg_hrv
        inputs.resting_hr = sleep.resting_hr
    if yesterday is not None:
        inputs.stress_avg = yesterday.stress_avg
    return inputs


def traffic_light_for(db: Session, day: date | None = None) -> dict:
    day = day or date.today()
    result = evaluate(build_inputs(db, day))
    result["date"] = day.isoformat()
    return result
