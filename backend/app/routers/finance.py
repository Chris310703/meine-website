"""Finanzen: Einnahmen und Ausgaben mit Kategorien, Monatsbudget, Übersicht."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import Transaction
from ..utils import MONTHS_DE, add_months, get_or_404, to_dict

router = APIRouter(prefix="/api/finance", tags=["Finanzen"])


class TransactionIn(BaseModel):
    date: Date
    amount: float = Field(gt=0)
    kind: str = Field(pattern=r"^(einnahme|ausgabe)$")
    category: str = "Sonstiges"
    description: str = ""


class TransactionPatch(BaseModel):
    date: Date | None = None
    amount: float | None = Field(default=None, gt=0)
    kind: str | None = Field(default=None, pattern=r"^(einnahme|ausgabe)$")
    category: str | None = None
    description: str | None = None


def month_bounds(month: str | None) -> tuple[date, date]:
    today = date.today()
    if month:
        try:
            y, m = (int(x) for x in month.split("-")[:2])
            start = date(y, m, 1)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Monat im Format JJJJ-MM angeben.") from exc
    else:
        start = today.replace(day=1)
    end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
    return start, end


def month_summary(db: Session, start: date, end: date) -> dict[str, Any]:
    rows = db.query(Transaction).filter(Transaction.date >= start, Transaction.date <= end).all()
    income = sum(t.amount for t in rows if t.kind == "einnahme")
    expense = sum(t.amount for t in rows if t.kind == "ausgabe")
    return {"income": round(income, 2), "expense": round(expense, 2), "saldo": round(income - expense, 2), "count": len(rows)}


@router.get("")
def finance(month: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    start, end = month_bounds(month)
    s = settings_store.get_all(db)
    rows = (
        db.query(Transaction)
        .filter(Transaction.date >= start, Transaction.date <= end)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    summary = month_summary(db, start, end)

    budgets: dict[str, float] = s["budget_categories"] or {}
    spent: dict[str, float] = defaultdict(float)
    income_by: dict[str, float] = defaultdict(float)
    for t in rows:
        if t.kind == "ausgabe":
            spent[t.category] += t.amount
        else:
            income_by[t.category] += t.amount
    categories = []
    for cat in sorted(set(budgets) | set(spent), key=lambda c: -spent.get(c, 0)):
        budget = budgets.get(cat)
        categories.append(
            {
                "category": cat,
                "spent": round(spent.get(cat, 0), 2),
                "budget": budget,
                "share": round(spent.get(cat, 0) / summary["expense"] * 100, 1) if summary["expense"] else 0,
                "over": bool(budget and spent.get(cat, 0) > budget),
            }
        )

    # Kumulierte Ausgaben im Monat vs. gleichmäßiges Budget
    days_in_month = end.day
    daily = defaultdict(float)
    for t in rows:
        if t.kind == "ausgabe":
            daily[t.date.day] += t.amount
    today = date.today()
    last_day = today.day if start <= today <= end else days_in_month if end < today else 0
    cumulative = []
    running = 0.0
    for d in range(1, days_in_month + 1):
        running += daily.get(d, 0)
        cumulative.append(
            {
                "day": d,
                "spent": round(running, 2) if d <= last_day else None,
                "budget_pace": round(s["monthly_budget"] * d / days_in_month, 2),
            }
        )

    # Übersicht der letzten 12 Monate
    months = []
    for i in range(11, -1, -1):
        m_start = add_months(start, -i)
        m_end = date(m_start.year, m_start.month, calendar.monthrange(m_start.year, m_start.month)[1])
        ms = month_summary(db, m_start, m_end)
        months.append({"month": m_start.strftime("%Y-%m"), "label": f"{MONTHS_DE[m_start.month - 1][:3]} {str(m_start.year)[2:]}", **ms})
    with_data = [m for m in months if m["count"]]

    return {
        "month": start.strftime("%Y-%m"),
        "month_label": f"{MONTHS_DE[start.month - 1]} {start.year}",
        "summary": summary,
        "budget": s["monthly_budget"],
        "budget_left": round(s["monthly_budget"] - summary["expense"], 2),
        "categories": categories,
        "income_by_category": [{"category": k, "amount": round(v, 2)} for k, v in sorted(income_by.items(), key=lambda x: -x[1])],
        "transactions": [to_dict(t) for t in rows],
        "cumulative": cumulative,
        "months": months,
        "avg_saldo": round(sum(m["saldo"] for m in with_data) / len(with_data), 2) if with_data else None,
        "expense_categories": list(budgets.keys()),
        "income_categories": s["income_categories"],
    }


@router.post("/transactions")
def create(payload: TransactionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = Transaction(**payload.model_dump())
    db.add(t)
    db.commit()
    return to_dict(t)


@router.patch("/transactions/{tx_id}")
def update(tx_id: int, payload: TransactionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Transaction, tx_id, "Buchung")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    return to_dict(t)


@router.delete("/transactions/{tx_id}")
def delete(tx_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Transaction, tx_id, "Buchung")
    db.delete(t)
    db.commit()
    return {"ok": True}
