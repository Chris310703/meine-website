"""Reine Umwandlungsfunktionen: Garmin-JSON → Felder unserer Tabellen.

Garmin liefert je nach Gerät/Firmware leicht unterschiedliche Strukturen,
deshalb wird hier alles defensiv mit .get() gelesen.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def _positive(value: Any) -> float | None:
    """Garmin nutzt -1/-2 als Platzhalter für „keine Daten“."""
    f = _num(value)
    if f is None or f < 0:
        return None
    return f


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        # Garmins "…Local"-Zeitstempel sind Millisekunden, bereits in Ortszeit verschoben
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
    text = str(value).replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_activity(a: dict[str, Any]) -> dict[str, Any] | None:
    activity_id = a.get("activityId")
    start = _parse_dt(a.get("startTimeLocal")) or _parse_dt(a.get("startTimeGMT"))
    if activity_id is None or start is None:
        return None
    type_key = (a.get("activityType") or {}).get("typeKey") or "other"
    distance = _positive(a.get("distance"))
    result: dict[str, Any] = {
        "garmin_id": str(activity_id),
        "start_time": start,
        "date": start.date(),
        "type": type_key,
        "name": a.get("activityName") or type_key,
        "duration_s": _positive(a.get("duration")) or _positive(a.get("elapsedDuration")) or 0.0,
        "distance_m": distance if distance else None,
        "avg_hr": _positive(a.get("averageHR")),
        "max_hr": _positive(a.get("maxHR")),
        "avg_speed": _positive(a.get("averageSpeed")),
        "calories": _positive(a.get("calories")),
        "training_load": _positive(a.get("activityTrainingLoad")),
        "aerobic_te": _positive(a.get("aerobicTrainingEffect")),
        "anaerobic_te": _positive(a.get("anaerobicTrainingEffect")),
        "elevation_gain": _positive(a.get("elevationGain")),
        "vo2max": _positive(a.get("vO2MaxValue")),
    }
    for zone in range(1, 6):
        result[f"z{zone}_s"] = _positive(a.get(f"hrTimeInZone_{zone}")) or 0.0
    return result


def has_zone_data(parsed: dict[str, Any]) -> bool:
    return any(parsed.get(f"z{z}_s") for z in range(1, 6))


def parse_hr_zones(data: Any) -> dict[str, float]:
    """Antwort von get_activity_hr_in_timezones → {"z1_s": …, …}."""
    zones = {f"z{z}_s": 0.0 for z in range(1, 6)}
    if not isinstance(data, list):
        return zones
    for item in data:
        number = item.get("zoneNumber")
        secs = _positive(item.get("secsInZone"))
        if isinstance(number, int) and 1 <= number <= 5 and secs is not None:
            zones[f"z{number}_s"] = secs
    return zones


def parse_user_summary(s: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    moderate = _positive(s.get("moderateIntensityMinutes")) or 0
    vigorous = _positive(s.get("vigorousIntensityMinutes")) or 0
    steps = _positive(s.get("totalSteps"))
    goal = _positive(s.get("dailyStepGoal"))
    return {
        "steps": int(steps) if steps is not None else None,
        "step_goal": int(goal) if goal is not None else None,
        "calories_total": _positive(s.get("totalKilocalories")),
        "calories_active": _positive(s.get("activeKilocalories")),
        "calories_bmr": _positive(s.get("bmrKilocalories")),
        "resting_hr": _positive(s.get("restingHeartRate")),
        "stress_avg": _positive(s.get("averageStressLevel")),
        "stress_max": _positive(s.get("maxStressLevel")),
        "body_battery_high": _positive(s.get("bodyBatteryHighestValue")),
        "body_battery_low": _positive(s.get("bodyBatteryLowestValue")),
        "body_battery_wake": _positive(s.get("bodyBatteryAtWakeTime")),
        "body_battery_charged": _positive(s.get("bodyBatteryChargedValue")),
        "body_battery_drained": _positive(s.get("bodyBatteryDrainedValue")),
        "intensity_minutes": moderate + 2 * vigorous if (moderate or vigorous) else None,
    }


def parse_sleep(d: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(d, dict):
        return None
    dto = d.get("dailySleepDTO") or {}
    duration = _positive(dto.get("sleepTimeSeconds"))
    cal = dto.get("calendarDate")
    if not duration or not cal:
        return None
    scores = dto.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    return {
        "date": date.fromisoformat(cal),
        "sleep_start": _parse_dt(dto.get("sleepStartTimestampLocal")),
        "sleep_end": _parse_dt(dto.get("sleepEndTimestampLocal")),
        "duration_s": duration,
        "deep_s": _positive(dto.get("deepSleepSeconds")) or 0.0,
        "light_s": _positive(dto.get("lightSleepSeconds")) or 0.0,
        "rem_s": _positive(dto.get("remSleepSeconds")) or 0.0,
        "awake_s": _positive(dto.get("awakeSleepSeconds")) or 0.0,
        "score": _positive(overall.get("value")),
        "score_qualifier": overall.get("qualifierKey"),
        "avg_hrv": _positive(d.get("avgOvernightHrv")),
        "resting_hr": _positive(d.get("restingHeartRate")),
    }


def parse_hrv(d: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(d, dict):
        return {}
    s = d.get("hrvSummary") or {}
    baseline = s.get("baseline") or {}
    status = s.get("status")
    return {
        "hrv_last_night": _positive(s.get("lastNightAvg")),
        "hrv_weekly_avg": _positive(s.get("weeklyAvg")),
        "hrv_baseline_low": _positive(baseline.get("balancedLow")),
        "hrv_baseline_high": _positive(baseline.get("balancedUpper")),
        "hrv_status": status.upper() if isinstance(status, str) else None,
    }


def parse_training_readiness(d: Any) -> dict[str, Any]:
    entries = d if isinstance(d, list) else [d] if isinstance(d, dict) else []
    entries = [e for e in entries if isinstance(e, dict) and e.get("score") is not None]
    if not entries:
        return {}
    # Morgendlichen Wert bevorzugen, sonst den jüngsten
    morning = [e for e in entries if e.get("inputContext") == "AFTER_WAKEUP_RESET"]
    entry = (morning or sorted(entries, key=lambda e: str(e.get("timestamp", "")), reverse=True))[0]
    recovery_min = _positive(entry.get("recoveryTime"))
    return {
        "training_readiness": _positive(entry.get("score")),
        "training_readiness_level": entry.get("level"),
        "recovery_time_h": round(recovery_min / 60, 1) if recovery_min is not None else None,
    }


TRAINING_STATUS_DE = {
    "PEAKING": "Höchstform",
    "PRODUCTIVE": "Produktiv",
    "MAINTAINING": "Erhaltend",
    "RECOVERY": "Erholung",
    "UNPRODUCTIVE": "Unproduktiv",
    "DETRAINING": "Leistungsabbau",
    "OVERREACHING": "Überlastung",
    "STRAINED": "Angestrengt",
    "NO_STATUS": "Kein Status",
}


def parse_training_status(d: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(d, dict):
        return {}
    result: dict[str, Any] = {}
    latest = ((d.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")) or {}
    device_entries = [v for v in latest.values() if isinstance(v, dict)] if isinstance(latest, dict) else []
    primary = next((e for e in device_entries if e.get("primaryTrainingDevice")), None)
    entry = primary or (device_entries[0] if device_entries else None)
    if entry:
        phrase = entry.get("trainingStatusFeedbackPhrase") or ""
        key = str(phrase).split("_")[0].upper() if phrase else ""
        if key:
            result["training_status"] = TRAINING_STATUS_DE.get(key, key.title())
        load = entry.get("acuteTrainingLoadDTO") or {}
        acute = _positive(load.get("dailyTrainingLoadAcute"))
        chronic = _positive(load.get("dailyTrainingLoadChronic"))
        ratio = _positive(load.get("dailyAcuteChronicWorkloadRatio"))
        if ratio is None and acute is not None and chronic:
            ratio = round(acute / chronic, 2)
        result.update({"acute_load": acute, "chronic_load": chronic, "acwr": ratio})
    vo2 = ((d.get("mostRecentVO2Max") or {}).get("generic")) or {}
    vo2_value = _positive(vo2.get("vo2MaxPreciseValue")) or _positive(vo2.get("vo2MaxValue"))
    if vo2_value:
        result["vo2max"] = round(vo2_value, 1)
    return result


def parse_max_metrics(d: Any) -> float | None:
    entries = d if isinstance(d, list) else [d] if isinstance(d, dict) else []
    for e in entries:
        generic = (e or {}).get("generic") or {}
        value = _positive(generic.get("vo2MaxPreciseValue")) or _positive(generic.get("vo2MaxValue"))
        if value:
            return round(value, 1)
    return None
