"""Tests für die Umwandlung der Garmin-Antworten."""

from datetime import date, datetime

from app.services import garmin_parse as gp


def test_parse_activity_running():
    raw = {
        "activityId": 123456,
        "activityName": "Morgenlauf",
        "startTimeLocal": "2026-09-20 07:15:00",
        "activityType": {"typeKey": "running"},
        "distance": 10234.5,
        "duration": 3120.4,
        "averageSpeed": 3.28,
        "averageHR": 142,
        "maxHR": 171,
        "calories": 710,
        "activityTrainingLoad": 98.4,
        "aerobicTrainingEffect": 3.1,
        "vO2MaxValue": 52,
        "hrTimeInZone_1": 300,
        "hrTimeInZone_2": 2200,
        "hrTimeInZone_3": 500,
        "hrTimeInZone_4": 100,
        "hrTimeInZone_5": 0,
    }
    a = gp.parse_activity(raw)
    assert a["garmin_id"] == "123456"
    assert a["start_time"] == datetime(2026, 9, 20, 7, 15)
    assert a["date"] == date(2026, 9, 20)
    assert a["type"] == "running"
    assert a["distance_m"] == 10234.5
    assert a["z2_s"] == 2200
    assert gp.has_zone_data(a)


def test_parse_activity_strength_without_distance():
    a = gp.parse_activity(
        {"activityId": 1, "startTimeLocal": "2026-09-20 18:00:00", "activityType": {"typeKey": "strength_training"}, "distance": 0, "duration": 3000}
    )
    assert a["distance_m"] is None
    assert not gp.has_zone_data(a)


def test_parse_activity_invalid_returns_none():
    assert gp.parse_activity({"activityName": "ohne ID"}) is None


def test_parse_hr_zones():
    zones = gp.parse_hr_zones([
        {"zoneNumber": 1, "secsInZone": 120.0},
        {"zoneNumber": 2, "secsInZone": 1800.0},
        {"zoneNumber": 6, "secsInZone": 5},
    ])
    assert zones == {"z1_s": 120.0, "z2_s": 1800.0, "z3_s": 0.0, "z4_s": 0.0, "z5_s": 0.0}


def test_parse_user_summary_ignores_placeholders():
    s = gp.parse_user_summary({
        "totalSteps": 11234,
        "dailyStepGoal": 10000,
        "totalKilocalories": 2840.0,
        "restingHeartRate": 49,
        "averageStressLevel": -1,
        "bodyBatteryHighestValue": 91,
        "bodyBatteryAtWakeTime": 88,
        "moderateIntensityMinutes": 20,
        "vigorousIntensityMinutes": 15,
    })
    assert s["steps"] == 11234
    assert s["stress_avg"] is None
    assert s["body_battery_wake"] == 88
    assert s["intensity_minutes"] == 50


def test_parse_sleep():
    raw = {
        "dailySleepDTO": {
            "calendarDate": "2026-09-21",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 6000,
            "awakeSleepSeconds": 1200,
            "sleepStartTimestampLocal": 1790460000000,
            "sleepEndTimestampLocal": 1790488200000,
            "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
        },
        "avgOvernightHrv": 58.0,
        "restingHeartRate": 48,
    }
    s = gp.parse_sleep(raw)
    assert s["date"] == date(2026, 9, 21)
    assert s["duration_s"] == 27000
    assert s["score"] == 82
    assert s["sleep_start"] < s["sleep_end"]
    assert gp.parse_sleep({"dailySleepDTO": {}}) is None


def test_parse_hrv():
    h = gp.parse_hrv({
        "hrvSummary": {
            "lastNightAvg": 61,
            "weeklyAvg": 58,
            "status": "balanced",
            "baseline": {"balancedLow": 50, "balancedUpper": 66},
        }
    })
    assert h == {
        "hrv_last_night": 61,
        "hrv_weekly_avg": 58,
        "hrv_baseline_low": 50,
        "hrv_baseline_high": 66,
        "hrv_status": "BALANCED",
    }
    assert gp.parse_hrv(None) == {}


def test_parse_training_readiness_prefers_morning():
    r = gp.parse_training_readiness([
        {"score": 60, "level": "MODERATE", "recoveryTime": 600, "timestamp": "2026-09-21T15:00:00"},
        {"score": 78, "level": "HIGH", "recoveryTime": 120, "inputContext": "AFTER_WAKEUP_RESET", "timestamp": "2026-09-21T07:00:00"},
    ])
    assert r["training_readiness"] == 78
    assert r["recovery_time_h"] == 2.0


def test_parse_training_status():
    raw = {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "3456": {
                    "primaryTrainingDevice": True,
                    "trainingStatusFeedbackPhrase": "PRODUCTIVE_3",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 520,
                        "dailyTrainingLoadChronic": 470,
                        "dailyAcuteChronicWorkloadRatio": 1.1,
                    },
                }
            }
        },
        "mostRecentVO2Max": {"generic": {"vo2MaxPreciseValue": 52.34}},
    }
    s = gp.parse_training_status(raw)
    assert s["training_status"] == "Produktiv"
    assert s["acute_load"] == 520
    assert s["acwr"] == 1.1
    assert s["vo2max"] == 52.3
