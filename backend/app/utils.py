"""Kleine Helfer für die API."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException


def to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    """SQLAlchemy-Objekt → JSON-taugliches Dict (Datumswerte als ISO-Text)."""
    exclude = exclude or set()
    out: dict[str, Any] = {}
    for column in obj.__table__.columns.keys():
        if column in exclude:
            continue
        value = getattr(obj, column)
        if isinstance(value, (datetime, date, time)):
            value = value.isoformat()
        out[column] = value
    return out


def get_or_404(db, model, pk, what: str = "Eintrag"):
    obj = db.get(model, pk)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{what} nicht gefunden.")
    return obj


def parse_date(value: str | None, default: date | None = None) -> date:
    if not value:
        if default is None:
            raise HTTPException(status_code=400, detail="Datum fehlt.")
        return default
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Ungültiges Datum: {value}") from exc


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def safe_mean(values) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def rnd(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
