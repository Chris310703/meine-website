"""Nährwerte: Mahlzeiten, Makros, Tagesziel, Bilanz gegenüber Garmin-Verbrauch, Wochenverlauf."""

from __future__ import annotations

from datetime import date, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import DailyMetrics, Meal
from ..utils import get_or_404, parse_date, to_dict
from .core import nutrition_day

router = APIRouter(prefix="/api/nutrition", tags=["Nährwerte"])

MEAL_TYPES = ["Frühstück", "Mittagessen", "Abendessen", "Snack"]


class MealIn(BaseModel):
    date: Date
    meal_type: str = "Snack"
    name: str = Field(min_length=1)
    kcal: float = Field(ge=0)
    protein: float = Field(default=0, ge=0)
    carbs: float = Field(default=0, ge=0)
    fat: float = Field(default=0, ge=0)


class MealPatch(BaseModel):
    date: Date | None = None
    meal_type: str | None = None
    name: str | None = None
    kcal: float | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)


@router.get("")
def nutrition(day: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = parse_date(day, date.today())
    meals = db.query(Meal).filter(Meal.date == d).order_by(Meal.created_at).all()
    by_type = {t: [] for t in MEAL_TYPES}
    for m in meals:
        by_type.setdefault(m.meal_type, []).append(to_dict(m))

    # Verlauf der letzten 14 Tage
    start = d - timedelta(days=13)
    history_meals = db.query(Meal).filter(Meal.date >= start, Meal.date <= d).all()
    metrics = {m.date: m for m in db.query(DailyMetrics).filter(DailyMetrics.date >= start, DailyMetrics.date <= d).all()}
    goal = settings_store.get(db, "kcal_goal")
    history = []
    for i in range(14):
        day_i = start + timedelta(days=i)
        ms = [m for m in history_meals if m.date == day_i]
        intake = sum(m.kcal for m in ms)
        burned = metrics[day_i].calories_total if day_i in metrics else None
        history.append(
            {
                "date": day_i.isoformat(),
                "intake": round(intake) if ms else None,
                "burned": round(burned) if burned else None,
                "balance": round(intake - burned) if ms and burned else None,
                "protein": round(sum(m.protein for m in ms)) if ms else None,
                "goal": goal,
            }
        )
    logged = [h for h in history[-7:] if h["intake"] is not None]
    avg7 = {
        "intake": round(sum(h["intake"] for h in logged) / len(logged)) if logged else None,
        "protein": round(sum(h["protein"] for h in logged) / len(logged)) if logged else None,
        "balance": round(sum(h["balance"] for h in logged if h["balance"] is not None) / max(1, len([h for h in logged if h["balance"] is not None])))
        if any(h["balance"] is not None for h in logged)
        else None,
        "days": len(logged),
    }

    # Häufige Mahlzeiten zum schnellen Eintragen
    recent = db.query(Meal).filter(Meal.date >= d - timedelta(days=45)).order_by(Meal.created_at.desc()).all()
    favorites: dict[str, dict[str, Any]] = {}
    for m in recent:
        f = favorites.setdefault(
            m.name,
            {"name": m.name, "meal_type": m.meal_type, "kcal": m.kcal, "protein": m.protein, "carbs": m.carbs, "fat": m.fat, "count": 0},
        )
        f["count"] += 1
    favs = sorted(favorites.values(), key=lambda f: -f["count"])[:12]

    return {
        "date": d.isoformat(),
        "summary": nutrition_day(db, d),
        "meals": by_type,
        "meal_types": MEAL_TYPES,
        "history": history,
        "avg_7": avg7,
        "favorites": favs,
    }


@router.post("/meals")
def add_meal(payload: MealIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = Meal(**payload.model_dump())
    db.add(m)
    db.commit()
    return to_dict(m)


@router.patch("/meals/{meal_id}")
def update_meal(meal_id: int, payload: MealPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = get_or_404(db, Meal, meal_id, "Mahlzeit")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return to_dict(m)


@router.delete("/meals/{meal_id}")
def delete_meal(meal_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = get_or_404(db, Meal, meal_id, "Mahlzeit")
    db.delete(m)
    db.commit()
    return {"ok": True}
