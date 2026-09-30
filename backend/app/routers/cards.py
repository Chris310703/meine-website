"""Karteikarten: Fächer → Themen → Karten, Abfrage mit Spaced Repetition, Import und Wochenrückblick."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CardReview, CardSubject, CardTopic, Flashcard
from ..services import claude_ai
from ..services import flashcards as srs
from ..utils import get_or_404, to_dict

router = APIRouter(prefix="/api/cards", tags=["Karteikarten"])

COLORS = ["#22d3ee", "#a78bfa", "#f472b6", "#facc15", "#34d399", "#fb923c", "#60a5fa", "#f87171"]
MATURE_DAYS = 21  # ab diesem Abstand „sitzt“ eine Karte


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _dt(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _state(c: Flashcard) -> srs.SrsState:
    return srs.SrsState(c.ease, c.interval_days, c.repetitions, c.lapses)


def _status(c: Flashcard, now: datetime) -> str:
    if c.due is None:
        return "neu"
    if c.due <= now:
        return "faellig"
    if c.interval_days >= MATURE_DAYS:
        return "sitzt"
    return "lernen"


def _counts(cards: list[Flashcard], now: datetime) -> dict[str, int]:
    out = {"total": len(cards), "neu": 0, "faellig": 0, "lernen": 0, "sitzt": 0}
    for c in cards:
        out[_status(c, now)] += 1
    return out


def serialize_card(c: Flashcard, now: datetime | None = None, with_preview: bool = False) -> dict[str, Any]:
    now = now or _now()
    d = to_dict(c)
    d["status"] = _status(c, now)
    d["topic"] = c.topic.name
    d["subject_id"] = c.topic.subject_id
    d["subject"] = c.topic.subject.name
    d["color"] = c.topic.subject.color
    if with_preview:
        d["preview"] = srs.preview(_state(c))
    return d


# ---------------------------------------------------------------- Übersicht


def _streak(db: Session, today: date) -> int:
    since = _dt(today - timedelta(days=400))
    days = {r[0].date() for r in db.query(CardReview.reviewed_at).filter(CardReview.reviewed_at >= since).all()}
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


@router.get("")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    now = _now()
    today = now.date()
    subjects = db.query(CardSubject).order_by(CardSubject.name).all()
    all_cards: list[Flashcard] = []
    out = []
    for s in subjects:
        topics = []
        s_cards: list[Flashcard] = []
        for t in s.topics:
            s_cards.extend(t.cards)
            topics.append({"id": t.id, "name": t.name, "order_index": t.order_index, "counts": _counts(t.cards, now)})
        all_cards.extend(s_cards)
        out.append({**to_dict(s), "topics": topics, "counts": _counts(s_cards, now)})

    forecast = []
    for i in range(7):
        day = today + timedelta(days=i)
        end = _dt(day + timedelta(days=1))
        n = sum(1 for c in all_cards if c.due is not None and c.due < end and (i == 0 or c.due >= _dt(day)))
        forecast.append({"date": day.isoformat(), "count": n})

    todays = db.query(CardReview).filter(CardReview.reviewed_at >= _dt(today)).all()
    return {
        "subjects": out,
        "counts": _counts(all_cards, now),
        "forecast": forecast,
        "today": {
            "reviews": len(todays),
            "correct": sum(1 for r in todays if r.correct),
            "wrong": sum(1 for r in todays if not r.correct),
        },
        "streak": _streak(db, today),
        "claude_available": claude_ai.available(),
        "claude_prompt": srs.CLAUDE_PROMPT,
    }


# ---------------------------------------------------------------- Fächer & Themen


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=9)
    emoji: str = Field(default="📚", max_length=8)


class SubjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=9)
    emoji: str | None = Field(default=None, max_length=8)


class TopicIn(BaseModel):
    subject_id: int
    name: str = Field(min_length=1, max_length=200)


class TopicPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject_id: int | None = None
    order_index: int | None = None


def _new_subject(db: Session, name: str, color: str | None = None, emoji: str = "📚") -> CardSubject:
    n = db.query(CardSubject).count()
    s = CardSubject(name=name.strip(), color=color or COLORS[n % len(COLORS)], emoji=emoji or "📚")
    db.add(s)
    db.flush()
    return s


def _new_topic(db: Session, subject: CardSubject, name: str) -> CardTopic:
    t = CardTopic(subject_id=subject.id, name=name.strip(), order_index=len(subject.topics))
    db.add(t)
    db.flush()
    db.refresh(subject)
    return t


@router.post("/subjects")
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = _new_subject(db, payload.name, payload.color, payload.emoji)
    db.commit()
    return to_dict(s)


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: int, payload: SubjectPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, CardSubject, subject_id, "Fach")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(s, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return to_dict(s)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.delete(get_or_404(db, CardSubject, subject_id, "Fach"))
    db.commit()
    return {"ok": True}


@router.post("/topics")
def create_topic(payload: TopicIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, CardSubject, payload.subject_id, "Fach")
    t = _new_topic(db, s, payload.name)
    db.commit()
    return to_dict(t)


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: TopicPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, CardTopic, topic_id, "Thema")
    data = payload.model_dump(exclude_unset=True)
    if data.get("subject_id") is not None:
        get_or_404(db, CardSubject, data["subject_id"], "Fach")
    for k, v in data.items():
        if v is not None:
            setattr(t, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return to_dict(t)


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.delete(get_or_404(db, CardTopic, topic_id, "Thema"))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Karten


class CardIn(BaseModel):
    topic_id: int
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)


class CardPatch(BaseModel):
    topic_id: int | None = None
    front: str | None = Field(default=None, min_length=1)
    back: str | None = Field(default=None, min_length=1)


def _parse_ids(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        return [int(x) for x in value.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Ungültige Themen-Auswahl.") from exc


def _scoped(db: Session, subject_id: int | None, topic_ids: list[int]):
    q = db.query(Flashcard).join(CardTopic)
    if topic_ids:
        q = q.filter(Flashcard.topic_id.in_(topic_ids))
    elif subject_id:
        q = q.filter(CardTopic.subject_id == subject_id)
    return q


@router.get("/list")
def list_cards(
    subject_id: int | None = None,
    topic_id: int | None = None,
    q: str = "",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    now = _now()
    cards = _scoped(db, subject_id, [topic_id] if topic_id else []).order_by(Flashcard.topic_id, Flashcard.id).all()
    if q.strip():
        words = q.lower().split()
        cards = [c for c in cards if all(w in f"{c.front} {c.back}".lower() for w in words)]
    return {"cards": [serialize_card(c, now) for c in cards]}


@router.post("/cards")
def create_card(payload: CardIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, CardTopic, payload.topic_id, "Thema")
    c = Flashcard(topic_id=payload.topic_id, front=payload.front.strip(), back=payload.back.strip())
    db.add(c)
    db.commit()
    return serialize_card(c)


@router.patch("/cards/{card_id}")
def update_card(card_id: int, payload: CardPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, Flashcard, card_id, "Karte")
    data = payload.model_dump(exclude_unset=True)
    if data.get("topic_id") is not None:
        get_or_404(db, CardTopic, data["topic_id"], "Thema")
    for k, v in data.items():
        if v is not None:
            setattr(c, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    db.refresh(c)
    return serialize_card(c)


@router.delete("/cards/{card_id}")
def delete_card(card_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.delete(get_or_404(db, Flashcard, card_id, "Karte"))
    db.commit()
    return {"ok": True}


@router.post("/cards/{card_id}/reset")
def reset_card(card_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Lernfortschritt zurücksetzen – die Karte gilt wieder als neu."""
    c = get_or_404(db, Flashcard, card_id, "Karte")
    c.ease, c.interval_days, c.repetitions, c.lapses, c.due = 2.5, 0, 0, 0, None
    db.commit()
    return serialize_card(c)


# ---------------------------------------------------------------- Abfrage


@router.get("/study")
def study(
    mode: str = "faellig",
    subject_id: int | None = None,
    topic_ids: str | None = None,
    new_limit: int = 20,
    limit: int = 200,
    shuffle: bool = True,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """mode=faellig: fällige Karten + bis zu `new_limit` neue (Spaced Repetition).
    mode=alle: alle Karten der Auswahl – z. B. kurz vor der Klausur."""
    now = _now()
    cards = _scoped(db, subject_id, _parse_ids(topic_ids)).all()
    if mode == "alle":
        chosen = list(cards)
        if shuffle:
            random.shuffle(chosen)
    else:
        due = sorted((c for c in cards if c.due is not None and c.due <= now), key=lambda c: c.due)
        new = sorted((c for c in cards if c.due is None), key=lambda c: (c.topic_id, c.id))[: max(0, new_limit)]
        if shuffle:
            random.shuffle(due)
        # Neue Karten gleichmäßig zwischen die Wiederholungen mischen
        chosen = []
        every = max(1, len(due) // len(new)) if new else 0
        pending = iter(new)
        for i, c in enumerate(due, 1):
            chosen.append(c)
            if every and i % every == 0 and (n := next(pending, None)):
                chosen.append(n)
        chosen.extend(pending)
    chosen = chosen[: max(1, limit)]
    return {"mode": mode, "cards": [serialize_card(c, now, with_preview=True) for c in chosen]}


class ReviewIn(BaseModel):
    grade: int = Field(ge=1, le=4)
    mode: str = "faellig"


@router.post("/cards/{card_id}/review")
def review(card_id: int, payload: ReviewIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, Flashcard, card_id, "Karte")
    now = _now()
    was_new = c.due is None
    # Im Modus „alle“ verschiebt eine richtige Antwort auf eine noch nicht fällige Karte den Plan nicht –
    # eine falsche Antwort holt sie aber zurück in die Wiederholung.
    early = payload.mode == "alle" and c.due is not None and c.due > now and c.repetitions > 0
    if not (early and payload.grade > 1):
        state, due = srs.schedule(_state(c), payload.grade, now)
        c.ease, c.interval_days, c.repetitions, c.lapses, c.due = state.ease, state.interval_days, state.repetitions, state.lapses, due
    c.last_reviewed = now
    db.add(
        CardReview(
            card_id=c.id,
            subject_id=c.topic.subject_id,
            topic_id=c.topic_id,
            reviewed_at=now,
            grade=payload.grade,
            correct=payload.grade >= 2,
            was_new=was_new,
            interval_after=c.interval_days,
        )
    )
    db.commit()
    return {"card": serialize_card(c, now, with_preview=True), "again": payload.grade == 1}


# ---------------------------------------------------------------- Import


class ImportIn(BaseModel):
    text: str = Field(min_length=1)
    subject_id: int | None = None
    topic_id: int | None = None
    subject_name: str = ""
    topic_name: str = ""
    dry_run: bool = False


def _resolve_targets(db: Session, payload: ImportIn, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordnet jeder Karte Fach und Thema zu (Angaben im Text haben Vorrang vor der Auswahl)."""
    default_subject = db.get(CardSubject, payload.subject_id) if payload.subject_id else None
    default_topic = db.get(CardTopic, payload.topic_id) if payload.topic_id else None
    if default_topic and not default_subject:
        default_subject = default_topic.subject
    out = []
    for p in parsed:
        subject = (p.get("subject") or "").strip() or (default_subject.name if default_subject else payload.subject_name.strip())
        topic = (p.get("topic") or "").strip()
        if not topic:
            if default_topic and (not p.get("subject") or p["subject"].strip().lower() == default_subject.name.lower()):
                topic = default_topic.name
            else:
                topic = payload.topic_name.strip() or "Allgemein"
        out.append({**p, "subject": subject, "topic": topic})
    return out


@router.post("/import")
def import_cards(payload: ImportIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    parsed = srs.parse_import(payload.text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Keine Karten erkannt. Nutze JSON (wie im Claude-Prompt), „F: … / A: …“ oder eine Zeile pro Karte: „Frage | Antwort“.",
        )
    cards = _resolve_targets(db, payload, parsed)
    if any(not c["subject"] for c in cards):
        raise HTTPException(status_code=400, detail="Bitte ein Fach auswählen oder im Text angeben (z. B. „# Fach: Zivilrecht“).")

    subjects = {s.name.lower(): s for s in db.query(CardSubject).all()}
    new_subjects = sorted({c["subject"] for c in cards if c["subject"].lower() not in subjects})
    new_topics: set[tuple[str, str]] = set()
    for c in cards:
        s = subjects.get(c["subject"].lower())
        if not s or not any(t.name.lower() == c["topic"].lower() for t in s.topics):
            new_topics.add((c["subject"], c["topic"]))

    if payload.dry_run:
        groups: dict[tuple[str, str], int] = defaultdict(int)
        for c in cards:
            groups[(c["subject"], c["topic"])] += 1
        return {
            "count": len(cards),
            "cards": cards[:300],
            "groups": [{"subject": s, "topic": t, "count": n, "new": (s, t) in new_topics} for (s, t), n in groups.items()],
            "new_subjects": new_subjects,
            "new_topics": [f"{s} → {t}" for s, t in sorted(new_topics)],
        }

    created = skipped = 0
    topic_cache: dict[tuple[str, str], CardTopic] = {}
    for c in cards:
        key = (c["subject"].lower(), c["topic"].lower())
        topic = topic_cache.get(key)
        if topic is None:
            s = subjects.get(key[0])
            if s is None:
                s = subjects[key[0]] = _new_subject(db, c["subject"])
            topic = next((t for t in s.topics if t.name.lower() == key[1]), None) or _new_topic(db, s, c["topic"])
            topic_cache[key] = topic
        existing = {f.front.strip().lower() for f in topic.cards}
        if c["front"].strip().lower() in existing:
            skipped += 1
            continue
        card = Flashcard(topic_id=topic.id, front=c["front"], back=c["back"])
        db.add(card)
        topic.cards.append(card)
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "new_subjects": new_subjects}


class GenerateIn(BaseModel):
    text: str = Field(min_length=20, max_length=200_000)
    count: int = Field(default=15, ge=3, le=80)


@router.post("/generate")
def generate(payload: GenerateIn) -> dict[str, Any]:
    """Lässt Claude (API) aus Notizen/Skript Karten im Importformat erzeugen – danach Vorschau & Import."""
    prompt = srs.CLAUDE_PROMPT.replace(
        "Erstelle Karteikarten", f"Erstelle etwa {payload.count} Karteikarten"
    ) + payload.text
    try:
        text = claude_ai.simple_completion(
            "Du bist ein Lerncoach für Recht und Wirtschaft und erstellst präzise, prüfungsnahe Karteikarten.",
            prompt,
            max_tokens=12000,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=claude_ai.friendly_error(exc)) from exc
    return {"text": text}


# ---------------------------------------------------------------- Wochenrückblick


def _week_totals(reviews: list[CardReview]) -> dict[str, Any]:
    correct = sum(1 for r in reviews if r.correct)
    return {
        "reviews": len(reviews),
        "correct": correct,
        "wrong": len(reviews) - correct,
        "accuracy": round(correct / len(reviews) * 100) if reviews else None,
        "cards": len({r.card_id for r in reviews if r.card_id}),
        "new_learned": sum(1 for r in reviews if r.was_new),
        "days_active": len({r.reviewed_at.date() for r in reviews}),
    }


def week_stats(db: Session, start: date, end: date) -> dict[str, Any]:
    reviews = (
        db.query(CardReview)
        .filter(CardReview.reviewed_at >= _dt(start), CardReview.reviewed_at < _dt(end + timedelta(days=1)))
        .all()
    )
    return {"reviews": reviews, "totals": _week_totals(reviews)}


@router.get("/week")
def week(offset: int = 0, db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=max(0, offset))
    end = start + timedelta(days=6)
    cur = week_stats(db, start, end)
    prev = week_stats(db, start - timedelta(weeks=1), start - timedelta(days=1))
    reviews: list[CardReview] = cur["reviews"]

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        rs = [r for r in reviews if r.reviewed_at.date() == d]
        days.append({"date": d.isoformat(), "correct": sum(1 for r in rs if r.correct), "wrong": sum(1 for r in rs if not r.correct)})

    subjects = {s.id: s for s in db.query(CardSubject).all()}
    topics = {t.id: t for t in db.query(CardTopic).all()}

    def breakdown(key: str) -> list[dict[str, Any]]:
        groups: dict[int | None, list[CardReview]] = defaultdict(list)
        for r in reviews:
            groups[getattr(r, key)].append(r)
        rows = []
        for gid, rs in groups.items():
            if key == "subject_id":
                s = subjects.get(gid)
                name, color, parent = (s.name, s.color, None) if s else ("Gelöschtes Fach", "#66788a", None)
            else:
                t = topics.get(gid)
                name = t.name if t else "Gelöschtes Thema"
                color = t.subject.color if t else "#66788a"
                parent = t.subject.name if t else None
            tot = _week_totals(rs)
            rows.append({"id": gid, "name": name, "color": color, "subject": parent, **tot})
        return sorted(rows, key=lambda r: -r["reviews"])

    wrong_per_card: dict[int, int] = defaultdict(int)
    for r in reviews:
        if not r.correct and r.card_id:
            wrong_per_card[r.card_id] += 1
    hardest = []
    for cid, n in sorted(wrong_per_card.items(), key=lambda x: -x[1])[:5]:
        c = db.get(Flashcard, cid)
        if c:
            hardest.append({"id": c.id, "front": c.front, "topic": c.topic.name, "color": c.topic.subject.color, "wrong": n})

    added = db.query(Flashcard).filter(Flashcard.created_at >= _dt(start), Flashcard.created_at < _dt(end + timedelta(days=1))).count()
    return {
        "offset": offset,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": f"KW {start.isocalendar()[1]} ({start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y')})",
        "totals": {**cur["totals"], "added": added},
        "previous": prev["totals"],
        "days": days,
        "subjects": breakdown("subject_id"),
        "topics": breakdown("topic_id"),
        "hardest": hardest,
    }
