"""Kalender per Link (iCal/ICS), z. B. FamilyWall."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import ics_calendars as svc

router = APIRouter(prefix="/api/ics", tags=["Kalender per Link"])


class FeedIn(BaseModel):
    name: str = Field(default="FamilyWall", max_length=80)
    url: str = Field(min_length=8, max_length=2000)


def _public(feed: dict[str, Any]) -> dict[str, Any]:
    # Der Link ist privat – nur gekürzt anzeigen
    url = feed["url"]
    return {**feed, "url": url[:38] + "…" if len(url) > 40 else url}


@router.get("")
def list_feeds(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"feeds": [_public(f) for f in svc.feeds(db)], "status": svc.status(), "refresh_minutes": svc.REFRESH_MINUTES}


@router.post("")
def add(payload: FeedIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        feed = svc.add_feed(db, payload.name, payload.url)
    except svc.IcsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.refresh_async()
    return _public(feed)


@router.delete("/{feed_id}")
def remove(feed_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    svc.remove_feed(db, feed_id)
    return {"ok": True}


@router.post("/refresh")
def refresh() -> dict[str, Any]:
    return {"started": svc.refresh_async(), "status": svc.status()}
