"""RSS-Feeds abrufen und Artikel ohne Duplikate speichern."""

from __future__ import annotations

import html
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import NewsFeed, NewsItem

log = logging.getLogger("lifeos.news")

REFRESH_AFTER = timedelta(minutes=30)
KEEP_DAYS = 30
_state: dict[str, Any] = {"running": False, "last_run": None}
_lock = threading.Lock()

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) LifeOS-Newsreader/1.0"


def clean_html(text: str, limit: int = 600) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _published(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                utc = datetime(*value[:6], tzinfo=timezone.utc)
                return utc.astimezone().replace(tzinfo=None)
            except (TypeError, ValueError):
                continue
    return None


def parse_feed(content: bytes) -> list[dict[str, Any]]:
    import feedparser

    parsed = feedparser.parse(content)
    items = []
    for e in parsed.entries:
        link = e.get("link")
        title = clean_html(e.get("title", ""), 300)
        if not link or not title:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "summary": clean_html(e.get("summary") or e.get("description") or ""),
                "published": _published(e),
            }
        )
    return items


def _download(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.content


def store_items(db: Session, feed: NewsFeed, items: list[dict[str, Any]]) -> int:
    new = 0
    for it in items:
        if db.query(NewsItem.id).filter(NewsItem.link == it["link"]).first():
            continue
        db.add(
            NewsItem(
                feed_id=feed.id,
                title=it["title"],
                link=it["link"],
                summary=it["summary"],
                published=it["published"] or datetime.now().replace(microsecond=0),
                category=feed.category,
            )
        )
        new += 1
    return new


def refresh_all(db: Session) -> dict[str, Any]:
    feeds = db.query(NewsFeed).filter(NewsFeed.active.is_(True)).all()
    results: dict[int, Any] = {}

    def fetch(feed_id: int, url: str):
        try:
            return feed_id, parse_feed(_download(url)), None
        except Exception as exc:
            return feed_id, [], str(exc)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for feed_id, items, error in pool.map(lambda f: fetch(f.id, f.url), feeds):
            results[feed_id] = (items, error)

    total_new = 0
    for feed in feeds:
        items, error = results.get(feed.id, ([], "kein Ergebnis"))
        feed.last_fetched = datetime.now().replace(microsecond=0)
        feed.last_error = f"Feed nicht erreichbar: {error}" if error else ""
        if not error:
            total_new += store_items(db, feed, items)
    # Alte Artikel und Beispielartikel entfernen, sobald echte Artikel da sind
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    db.execute(delete(NewsItem).where(NewsItem.published < cutoff, NewsItem.is_demo.is_(False)))
    if total_new:
        db.execute(delete(NewsItem).where(NewsItem.is_demo.is_(True)))
    db.commit()
    return {"new": total_new, "feeds": len(feeds), "errors": sum(1 for f in feeds if f.last_error)}


def needs_refresh(db: Session) -> bool:
    last = db.query(NewsFeed.last_fetched).filter(NewsFeed.active.is_(True)).order_by(NewsFeed.last_fetched.desc()).first()
    return last is None or last[0] is None or datetime.now() - last[0] > REFRESH_AFTER


def refresh_async() -> bool:
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
    threading.Thread(target=_run, daemon=True).start()
    return True


def _run() -> None:
    try:
        with SessionLocal() as db:
            _state["last_result"] = refresh_all(db)
    except Exception as exc:  # pragma: no cover
        log.warning("News-Abruf fehlgeschlagen: %s", exc)
    finally:
        _state["running"] = False
        _state["last_run"] = datetime.now().replace(microsecond=0).isoformat()


def status() -> dict[str, Any]:
    return dict(_state)
