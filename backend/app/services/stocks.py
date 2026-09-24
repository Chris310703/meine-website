"""Aktienkurse über yfinance, zwischengespeichert in SQLite (funktioniert auch offline mit dem letzten Stand)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import PriceCache, StockPosition

log = logging.getLogger("lifeos.stocks")
# yfinance meldet jeden fehlgeschlagenen Abruf sehr ausführlich – das behandeln wir selbst
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STALE_AFTER = timedelta(minutes=15)
_state: dict[str, Any] = {"running": False, "last_error": "", "last_run": None}
_lock = threading.Lock()


def fx_symbol(currency: str) -> str | None:
    cur = (currency or "EUR").upper()
    if cur in ("EUR", ""):
        return None
    if cur == "GBX":
        cur = "GBP"
    return f"EUR{cur}=X"


def to_eur(value: float | None, currency: str | None, rates: dict[str, float]) -> float | None:
    """Rechnet einen Betrag in Euro um. rates: {"USD": 1.12} = 1 EUR kostet 1,12 USD."""
    if value is None:
        return None
    cur = (currency or "EUR")
    if cur == "GBp":  # Londoner Kurse in Pence
        value, cur = value / 100, "GBP"
    cur = cur.upper()
    if cur == "EUR":
        return value
    rate = rates.get(cur)
    return value / rate if rate else None


def fx_rates(db: Session, currencies: set[str]) -> dict[str, float]:
    rates = {}
    for cur in currencies:
        sym = fx_symbol(cur if cur != "GBp" else "GBP")
        if not sym:
            continue
        row = db.get(PriceCache, sym)
        if row and row.price:
            rates[cur.upper() if cur != "GBp" else "GBP"] = row.price
    return rates


def is_stale(db: Session) -> bool:
    symbols = {p.symbol for p in db.query(StockPosition).all()}
    if not symbols:
        return False
    for sym in symbols:
        row = db.get(PriceCache, sym)
        if row is None or row.updated_at is None or datetime.now() - row.updated_at > STALE_AFTER:
            return True
    return False


def status() -> dict[str, Any]:
    return dict(_state)


def can_retry() -> bool:
    """Nach einem Abruf mindestens 5 Minuten warten (schont Yahoo und die Laufzeit offline)."""
    last = _state.get("last_run")
    return last is None or datetime.now() - datetime.fromisoformat(last) > timedelta(minutes=5)


def refresh_async() -> bool:
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, last_error="")
    threading.Thread(target=_run_refresh, daemon=True).start()
    return True


def _run_refresh() -> None:
    try:
        with SessionLocal() as db:
            refresh(db)
    except Exception as exc:  # Netzwerk, Yahoo-Änderungen …
        log.warning("Kursabruf fehlgeschlagen: %s", exc)
        _state["last_error"] = f"Kurse konnten nicht geladen werden: {exc}"
    finally:
        _state["running"] = False
        _state["last_run"] = datetime.now().replace(microsecond=0).isoformat()


def refresh(db: Session) -> int:
    import yfinance as yf

    positions = db.query(StockPosition).all()
    symbols = sorted({p.symbol.upper() for p in positions})
    currencies = {p.currency for p in positions}
    fx = sorted({s for s in (fx_symbol(c) for c in currencies) if s})
    tickers = symbols + fx
    if not tickers:
        return 0
    data = yf.download(tickers, period="1y", interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    updated = 0
    errors = []
    for sym in tickers:
        try:
            frame = data[sym] if len(tickers) > 1 else data
            closes = frame["Close"].dropna()
        except Exception:
            errors.append(sym)
            continue
        if closes.empty:
            errors.append(sym)
            continue
        history = [[idx.date().isoformat(), round(float(v), 4)] for idx, v in closes.items()]
        price = history[-1][1]
        prev = history[-2][1] if len(history) > 1 else None
        currency = None
        name = None
        try:
            fi = yf.Ticker(sym).fast_info
            price = float(fi.get("lastPrice") or price)
            prev = float(fi.get("previousClose") or prev) if (fi.get("previousClose") or prev) else None
            currency = fi.get("currency")
        except Exception:
            pass
        row = db.get(PriceCache, sym)
        if row is None:
            row = PriceCache(symbol=sym)
            db.add(row)
        row.price = round(price, 4)
        row.prev_close = prev
        row.currency = currency or row.currency
        row.name = name or row.name
        row.history = history
        row.source = "yfinance"
        row.updated_at = datetime.now().replace(microsecond=0)
        updated += 1
    db.commit()
    if errors and updated == 0:
        _state["last_error"] = "Yahoo Finance ist gerade nicht erreichbar – angezeigt werden die zuletzt gespeicherten Kurse."
    elif errors:
        _state["last_error"] = "Keine Kurse gefunden für: " + ", ".join(errors) + " (Symbol prüfen, z. B. SAP.DE für Xetra)."
    return updated


def lookup_name(symbol: str) -> str | None:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info
        return info.get("shortName") or info.get("longName")
    except Exception:
        return None
