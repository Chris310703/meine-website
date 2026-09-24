"""News aus RSS-Feeds, nach Kategorien gefiltert."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import NewsFeed, NewsItem
from ..services import news as svc
from ..utils import get_or_404, to_dict

router = APIRouter(prefix="/api/news", tags=["News"])


class FeedIn(BaseModel):
    name: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://")
    category: str = "Allgemein"
    active: bool = True


class FeedPatch(BaseModel):
    name: str | None = None
    url: str | None = Field(default=None, pattern=r"^https?://")
    category: str | None = None
    active: bool | None = None


@router.get("")
def news(category: str | None = None, q: str = "", limit: int = 120, db: Session = Depends(get_db)) -> dict[str, Any]:
    if svc.needs_refresh(db):
        svc.refresh_async()
    query = db.query(NewsItem).join(NewsFeed).filter(NewsFeed.active.is_(True))
    if category:
        query = query.filter(NewsItem.category == category)
    items = query.order_by(NewsItem.published.desc()).limit(600).all()
    if q.strip():
        words = q.lower().split()
        items = [i for i in items if all(w in f"{i.title} {i.summary}".lower() for w in words)]
    feeds = db.query(NewsFeed).order_by(NewsFeed.category, NewsFeed.name).all()
    counts: dict[str, int] = {}
    for c, in db.query(NewsItem.category).join(NewsFeed).filter(NewsFeed.active.is_(True)).all():
        counts[c] = counts.get(c, 0) + 1
    return {
        "items": [{**to_dict(i), "feed": i.feed.name} for i in items[:limit]],
        "categories": sorted({f.category for f in feeds}),
        "counts": counts,
        "feeds": [to_dict(f) for f in feeds],
        "status": svc.status(),
        "demo": any(i.is_demo for i in items),
    }


@router.post("/refresh")
def refresh() -> dict[str, Any]:
    return {"started": svc.refresh_async(), "status": svc.status()}


@router.get("/feeds")
def feeds(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [to_dict(f) for f in db.query(NewsFeed).order_by(NewsFeed.category, NewsFeed.name).all()]


@router.post("/feeds")
def create_feed(payload: FeedIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    f = NewsFeed(**payload.model_dump())
    db.add(f)
    db.commit()
    svc.refresh_async()
    return to_dict(f)


@router.patch("/feeds/{feed_id}")
def update_feed(feed_id: int, payload: FeedPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    f = get_or_404(db, NewsFeed, feed_id, "Feed")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    if payload.category is not None:
        db.query(NewsItem).filter(NewsItem.feed_id == f.id).update({NewsItem.category: payload.category})
    db.commit()
    return to_dict(f)


@router.delete("/feeds/{feed_id}")
def delete_feed(feed_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    f = get_or_404(db, NewsFeed, feed_id, "Feed")
    db.delete(f)
    db.commit()
    return {"ok": True}
