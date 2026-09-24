"""Auswertungen für den Fitness-Reiter (reine Funktionen, gut testbar)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

RUN_TYPES = {"running", "trail_running", "treadmill_running", "track_running", "virtual_run"}
BIKE_TYPES = {"cycling", "road_biking", "indoor_cycling", "mountain_biking", "gravel_cycling", "virtual_ride"}
STRENGTH_TYPES = {"strength_training", "hiit", "indoor_cardio", "cardio"}


def category(type_key: str) -> str:
    if type_key in RUN_TYPES:
        return "laufen"
    if type_key in BIKE_TYPES:
        return "rad"
    if type_key in STRENGTH_TYPES:
        return "kraft"
    if "swim" in type_key:
        return "schwimmen"
    return "sonstiges"


def zone_bounds(max_hr: float, limits_pct: list[float]) -> list[tuple[int, int]]:
    """Grenzen der HF-Zonen in bpm, z. B. [(117, 136), (137, 156), …]."""
    bounds = []
    lower = 50.0
    for upper in limits_pct:
        bounds.append((round(max_hr * lower / 100), round(max_hr * upper / 100)))
        lower = upper
    return bounds


@dataclass
class RunSample:
    day: date
    speed: float  # m/s
    avg_hr: float
    z2_share: float  # Anteil Zeit in Zone 2 (0–1)
    duration_s: float


def pace_at_reference_hr(speed: float, avg_hr: float, reference_hr: float) -> float:
    """Normalisiert die Pace auf eine Referenz-Herzfrequenz (min/km).

    Annahme: Geschwindigkeit pro Herzschlag ist im aeroben Bereich annähernd konstant
    (Efficiency Factor). pace_ref = 1000 / (speed × ref/hr) / 60.
    """
    speed_at_ref = speed * reference_hr / avg_hr
    return 1000 / speed_at_ref / 60


def is_z2_run(sample: RunSample, z2_low: float, z2_high: float) -> bool:
    if sample.duration_s < 20 * 60:
        return False
    in_band = z2_low - 3 <= sample.avg_hr <= z2_high + 3
    return in_band or sample.z2_share >= 0.6


def linear_trend(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def z2_pace_trend(samples: list[RunSample], z2_low: float, z2_high: float, reference_hr: float) -> dict:
    points = []
    for s in sorted(samples, key=lambda x: x.day):
        if not s.speed or not s.avg_hr or not is_z2_run(s, z2_low, z2_high):
            continue
        points.append(
            {
                "date": s.day.isoformat(),
                "pace": round(1000 / s.speed / 60, 3),
                "hr": round(s.avg_hr),
                "pace_ref": round(pace_at_reference_hr(s.speed, s.avg_hr, reference_hr), 3),
            }
        )
    result = {"points": points, "reference_hr": reference_hr, "change_sec_per_km_per_month": None}
    if len(points) >= 3:
        t0 = date.fromisoformat(points[0]["date"])
        xs = [(date.fromisoformat(p["date"]) - t0).days for p in points]
        ys = [p["pace_ref"] for p in points]
        trend = linear_trend(xs, ys)
        if trend:
            slope, intercept = trend
            for p, x in zip(points, xs):
                p["trend"] = round(intercept + slope * x, 3)
            result["change_sec_per_km_per_month"] = round(slope * 30 * 60, 1)
    return result


def week_key(d: date) -> date:
    return d - timedelta(days=d.weekday())
