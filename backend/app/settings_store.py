"""Einstellungen (Ziele, Lernplan-Parameter …) als Schlüssel/Wert-Paare in SQLite."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from .models import Setting

DEFAULT_SETTINGS: dict[str, Any] = {
    "profile_name": "Chris",
    # Schlaf
    "sleep_goal_hours": 8.0,
    "bedtime_target": "23:00",
    "wake_target": "07:00",
    # Ernährung
    "kcal_goal": 2600,
    "protein_goal": 150,
    "carbs_goal": 300,
    "fat_goal": 80,
    # Training
    "weekly_run_km_goal": 30,
    "weekly_training_hours_goal": 5,
    "weekly_sessions_goal": 4,
    "max_hr": 195,
    "z2_reference_hr": 140,
    # Obergrenzen der HF-Zonen 1–5 in % der maximalen Herzfrequenz
    "hr_zone_limits": [60, 70, 80, 90, 100],
    # Finanzen
    "monthly_budget": 950,
    "currency": "EUR",
    "budget_categories": {
        "Miete & Wohnen": 420,
        "Lebensmittel": 220,
        "Mobilität": 60,
        "Freizeit": 90,
        "Uni & Bücher": 40,
        "Sport": 45,
        "Abos": 25,
        "Sonstiges": 50,
    },
    "income_categories": ["Werkstudentenjob", "Eltern", "BAföG/Stipendium", "Sonstiges"],
    # Lernplan
    "study": {
        "day_start": "08:00",
        "day_end": "21:00",
        "max_minutes_per_day": 300,
        "block_minutes": 90,
        "min_block_minutes": 45,
        "break_minutes": 15,
        "buffer_days": 2,
        "review_intervals": [1, 3, 7],
        "review_minutes": 45,
        "event_padding_minutes": 15,
        "workout_padding_minutes": 30,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "max_blocks_per_subject_per_day": 3,
    },
    # Semester für den Stundenplan
    "semester": {"name": "Wintersemester", "start": None, "end": None},
    # Google Kalender
    "google_read_calendars": [],
    "google_study_calendar_id": None,
    "google_auto_push": True,
    # Garmin
    "garmin_auto_sync": True,
    "garmin_sync_days": 14,
    # Journal-Leitfragen
    "journal_questions": {
        "morgen": [
            "Wofür bin ich heute dankbar?",
            "Was ist heute meine wichtigste Aufgabe?",
            "Wie will ich mich heute fühlen?",
        ],
        "abend": [
            "Was ist heute gut gelaufen?",
            "Was habe ich gelernt?",
            "Was mache ich morgen besser?",
        ],
    },
    "todo_categories": ["Uni", "Privat", "Job", "Sport", "Finanzen"],
}


def get_all(db: Session) -> dict[str, Any]:
    values = copy.deepcopy(DEFAULT_SETTINGS)
    for row in db.query(Setting).all():
        default = values.get(row.key)
        if isinstance(default, dict) and isinstance(row.value, dict) and row.key == "study":
            merged = dict(default)
            merged.update(row.value)
            values[row.key] = merged
        else:
            values[row.key] = row.value
    return values


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    if row is not None:
        if key == "study" and isinstance(row.value, dict):
            merged = dict(DEFAULT_SETTINGS["study"])
            merged.update(row.value)
            return merged
        return row.value
    if key in DEFAULT_SETTINGS:
        return copy.deepcopy(DEFAULT_SETTINGS[key])
    return default


def set_value(db: Session, key: str, value: Any, commit: bool = True) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    if commit:
        db.commit()


def update_many(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        set_value(db, key, value, commit=False)
    db.commit()
    return get_all(db)
