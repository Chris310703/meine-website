"""Tests für Fitness-, Schlaf- und Habit-Auswertungen."""

from datetime import date, datetime, timedelta

from app.routers.sleep import clock_minutes, regularity
from app.models import SleepRecord
from app.services.fitness_stats import RunSample, pace_at_reference_hr, z2_pace_trend, zone_bounds
from app.services.habits_logic import current_streak, longest_streak


def test_zone_bounds():
    assert zone_bounds(200, [60, 70, 80, 90, 100]) == [(100, 120), (120, 140), (140, 160), (160, 180), (180, 200)]


def test_pace_normalisation():
    # 3 m/s bei 150 bpm → auf 140 bpm normalisiert langsamer
    real = 1000 / 3 / 60
    assert pace_at_reference_hr(3.0, 150, 140) > real
    assert abs(pace_at_reference_hr(3.0, 140, 140) - real) < 1e-9


def test_z2_trend_detects_improvement():
    start = date(2026, 6, 1)
    samples = [
        # jede Woche bei gleichem Puls etwas schneller
        RunSample(start + timedelta(days=7 * i), 2.70 + 0.03 * i, 140, 0.8, 3000)
        for i in range(8)
    ]
    samples.append(RunSample(start, 4.2, 170, 0.05, 1500))  # Intervall-Einheit wird ignoriert
    result = z2_pace_trend(samples, 128, 146, 140)
    assert len(result["points"]) == 8
    assert result["change_sec_per_km_per_month"] < 0  # schneller = weniger Sekunden pro km
    assert "trend" in result["points"][0]


def test_clock_minutes():
    assert clock_minutes(datetime(2026, 1, 1, 23, 30)) == -30
    assert clock_minutes(datetime(2026, 1, 2, 0, 45)) == 45
    assert clock_minutes(datetime(2026, 1, 2, 7, 0)) == 420


def test_sleep_regularity():
    def rec(day, bed_h, bed_m, wake_h):
        d = date(2026, 9, day)
        return SleepRecord(
            date=d,
            sleep_start=datetime(2026, 9, day - 1, bed_h, bed_m),
            sleep_end=datetime(2026, 9, day, wake_h, 0),
            duration_s=8 * 3600,
        )

    steady = [rec(d, 23, 0, 7) for d in range(10, 17)]
    assert regularity(steady)["score"] == 100
    chaotic = [rec(10, 22, 0, 6), rec(11, 23, 59, 9), rec(12, 21, 30, 5), rec(13, 23, 45, 10)]
    assert regularity(chaotic)["score"] < 60
    assert regularity(steady[:2])["score"] is None


def test_habit_streaks():
    today = date(2026, 9, 24)
    days = {today - timedelta(days=i) for i in range(5)}
    assert current_streak(days, today) == 5
    # heute noch offen → Serie bis gestern zählt weiter
    assert current_streak(days - {today}, today) == 4
    assert current_streak(set(), today) == 0
    assert longest_streak(days | {today - timedelta(days=10), today - timedelta(days=11)}) == 5
