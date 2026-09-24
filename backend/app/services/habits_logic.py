"""Streak-Berechnung für Habits."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


def current_streak(done_dates: Iterable[date], today: date) -> int:
    """Aufeinanderfolgende Tage bis heute. Ist heute noch offen, zählt die Serie bis gestern."""
    days = set(done_dates)
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(done_dates: Iterable[date]) -> int:
    days = sorted(set(done_dates))
    best = run = 0
    prev: date | None = None
    for d in days:
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best
