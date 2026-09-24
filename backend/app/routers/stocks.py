"""Aktien: Depot und Watchlist, aktuelle Kurse, Gewinn/Verlust, Kursverläufe."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import PriceCache, StockPosition
from ..services import stocks as svc
from ..utils import get_or_404, to_dict

router = APIRouter(prefix="/api/stocks", tags=["Aktien"])

PERIODS = {"1m": 31, "3m": 92, "6m": 183, "1j": 366}


class PositionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    name: str = ""
    kind: str = Field(default="depot", pattern=r"^(depot|watchlist)$")
    quantity: float = Field(default=0, ge=0)
    buy_price: float | None = Field(default=None, ge=0)
    buy_date: Date | None = None
    currency: str = "EUR"
    notes: str = ""


class PositionPatch(BaseModel):
    name: str | None = None
    kind: str | None = Field(default=None, pattern=r"^(depot|watchlist)$")
    quantity: float | None = Field(default=None, ge=0)
    buy_price: float | None = Field(default=None, ge=0)
    buy_date: Date | None = None
    currency: str | None = None
    notes: str | None = None


def _history_since(history: list | None, days: int) -> list:
    if not history:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [h for h in history if h[0] >= cutoff]


@router.get("")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    if svc.is_stale(db) and svc.can_retry():
        svc.refresh_async()
    positions = db.query(StockPosition).order_by(StockPosition.kind, StockPosition.symbol).all()
    rates = svc.fx_rates(db, {p.currency for p in positions})
    rows = []
    depot_value = invested = day_change = 0.0
    value_series: dict[str, float] = defaultdict(float)
    demo_prices = False
    for p in positions:
        cache = db.get(PriceCache, p.symbol.upper())
        price = cache.price if cache else None
        prev = cache.prev_close if cache else None
        currency = (cache.currency if cache and cache.currency else p.currency) or "EUR"
        if cache and cache.source == "demo":
            demo_prices = True
        change_pct = (price / prev - 1) * 100 if price and prev else None
        value = price * p.quantity if price is not None and p.kind == "depot" else None
        cost = p.buy_price * p.quantity if p.buy_price is not None and p.kind == "depot" else None
        value_eur = svc.to_eur(value, currency, rates)
        cost_eur = svc.to_eur(cost, currency, rates)
        pl = value - cost if value is not None and cost is not None else None
        if p.kind == "depot" and value_eur is not None:
            depot_value += value_eur
            invested += cost_eur or 0
            if prev:
                day_change += svc.to_eur((price - prev) * p.quantity, currency, rates) or 0
            for d, close in _history_since(cache.history if cache else None, 366):
                value_series[d] += svc.to_eur(close * p.quantity, currency, rates) or 0
        rows.append(
            {
                **to_dict(p),
                "name": p.name or (cache.name if cache else "") or p.symbol,
                "price": price,
                "prev_close": prev,
                "price_currency": currency,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "value": round(value, 2) if value is not None else None,
                "value_eur": round(value_eur, 2) if value_eur is not None else None,
                "cost": round(cost, 2) if cost is not None else None,
                "pl": round(pl, 2) if pl is not None else None,
                "pl_pct": round(pl / cost * 100, 2) if pl is not None and cost else None,
                "spark": [h[1] for h in _history_since(cache.history if cache else None, 31)],
                "updated_at": cache.updated_at.isoformat() if cache and cache.updated_at else None,
                "source": cache.source if cache else None,
            }
        )
    depot = [r for r in rows if r["kind"] == "depot"]
    allocation = [
        {"symbol": r["symbol"], "name": r["name"], "value_eur": r["value_eur"], "share": round(r["value_eur"] / depot_value * 100, 1) if depot_value and r["value_eur"] else 0}
        for r in sorted(depot, key=lambda r: -(r["value_eur"] or 0))
    ]
    series = [{"date": d, "value": round(v, 2)} for d, v in sorted(value_series.items())]
    return {
        "positions": rows,
        "totals": {
            "value": round(depot_value, 2),
            "invested": round(invested, 2),
            "pl": round(depot_value - invested, 2),
            "pl_pct": round((depot_value / invested - 1) * 100, 2) if invested else None,
            "day_change": round(day_change, 2),
        },
        "allocation": allocation,
        "value_history": series,
        "fx": rates,
        "status": svc.status(),
        "demo_prices": demo_prices,
    }


@router.get("/history/{symbol}")
def history(symbol: str, period: str = "1j", db: Session = Depends(get_db)) -> dict[str, Any]:
    cache = db.get(PriceCache, symbol.upper())
    days = PERIODS.get(period, 366)
    data = _history_since(cache.history if cache else None, days)
    return {"symbol": symbol.upper(), "period": period, "points": [{"date": d, "close": c} for d, c in data], "currency": cache.currency if cache else None}


def _fill_name(position_id: int) -> None:
    with SessionLocal() as db:
        p = db.get(StockPosition, position_id)
        if p and not p.name:
            name = svc.lookup_name(p.symbol)
            if name:
                p.name = name
                db.commit()


@router.post("/positions")
def create(payload: PositionIn, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = payload.model_dump()
    data["symbol"] = data["symbol"].strip().upper()
    data["currency"] = (data["currency"] or "EUR").upper()
    if data["kind"] == "depot" and data["quantity"] <= 0:
        raise HTTPException(status_code=400, detail="Für das Depot bitte eine Stückzahl > 0 angeben.")
    p = StockPosition(**data)
    db.add(p)
    db.commit()
    if not p.name:
        background.add_task(_fill_name, p.id)
    svc.refresh_async()
    return to_dict(p)


@router.patch("/positions/{position_id}")
def update(position_id: int, payload: PositionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, StockPosition, position_id, "Position")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return to_dict(p)


@router.delete("/positions/{position_id}")
def delete(position_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, StockPosition, position_id, "Position")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/refresh")
def refresh() -> dict[str, Any]:
    return {"started": svc.refresh_async(), "status": svc.status()}


@router.get("/status")
def status() -> dict[str, Any]:
    return svc.status()
