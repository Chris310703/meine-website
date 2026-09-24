"""Lernplan: Fächer, Prüfungstermine, Unterlagen, Themen (manuell oder per Claude), Lernblöcke."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from datetime import date as Date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import FocusSession, StudyBlock, StudyDocument, Subject, Topic
from ..services import claude_ai, documents, google_calendar, study_service
from ..services.study_service import serialize_block
from ..utils import get_or_404, parse_date, to_dict

router = APIRouter(prefix="/api/study", tags=["Lernplan"])
log = logging.getLogger("lifeos.study")

SUBJECT_COLORS = ["#38bdf8", "#a3e635", "#facc15", "#c084fc", "#fb7185", "#34d399", "#f97316", "#60a5fa"]


def _replan_and_push(db: Session) -> dict[str, Any]:
    result = study_service.replan(db)
    settings_store.set_value(
        db,
        "last_plan",
        {"at": datetime.now().replace(microsecond=0).isoformat(), "warnings": result["warnings"], "created": result["created"], "missed": result["missed"]},
    )
    google_calendar.push_if_enabled(db)
    return result


# ---------------------------------------------------------------- Übersicht


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    now = datetime.now()
    # Verpasste Blöcke automatisch neu einplanen
    if db.query(StudyBlock).filter(StudyBlock.status == "geplant", StudyBlock.end < now).first():
        _replan_and_push(db)
    horizon = now + timedelta(days=21)
    upcoming = (
        db.query(StudyBlock)
        .filter(StudyBlock.end >= now - timedelta(days=7), StudyBlock.start <= horizon)
        .order_by(StudyBlock.start)
        .all()
    )
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_blocks = db.query(StudyBlock).filter(
        StudyBlock.start >= datetime.combine(week_start, datetime.min.time()),
        StudyBlock.start < datetime.combine(week_start + timedelta(days=7), datetime.min.time()),
    ).all()

    def minutes(blocks):
        return sum(int((b.end - b.start).total_seconds() // 60) for b in blocks)

    focus_week = db.query(FocusSession).filter(FocusSession.start >= datetime.combine(week_start, datetime.min.time())).all()
    return {
        "subjects": study_service.subject_overview(db, today),
        "blocks": [serialize_block(b) for b in upcoming],
        "last_plan": settings_store.get(db, "last_plan"),
        "week": {
            "planned_minutes": minutes([b for b in week_blocks if b.status != "verpasst"]),
            "done_minutes": minutes([b for b in week_blocks if b.status == "erledigt"]),
            "missed": sum(1 for b in week_blocks if b.status == "verpasst"),
            "focus_minutes": round(sum(f.minutes for f in focus_week)),
        },
        "claude_available": claude_ai.available(),
        "google_connected": google_calendar.is_connected(),
        "settings": settings_store.get(db, "study"),
    }


@router.post("/replan")
def replan(db: Session = Depends(get_db)) -> dict[str, Any]:
    return _replan_and_push(db)


# ---------------------------------------------------------------- Fächer


class SubjectIn(BaseModel):
    name: str = Field(min_length=1)
    short: str = ""
    color: str | None = None
    exam_date: Date | None = None
    exam_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    exam_location: str = ""
    study_start: Date | None = None
    notes: str = ""
    active: bool = True


class SubjectPatch(BaseModel):
    name: str | None = None
    short: str | None = None
    color: str | None = None
    exam_date: Date | None = None
    exam_time: str | None = Field(default=None, pattern=r"^(\d{2}:\d{2})?$")
    exam_location: str | None = None
    study_start: Date | None = None
    notes: str | None = None
    active: bool | None = None


@router.get("/subjects")
def subjects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [to_dict(s) for s in db.query(Subject).order_by(Subject.name).all()]


@router.post("/subjects")
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = payload.model_dump()
    if not data["color"]:
        data["color"] = SUBJECT_COLORS[db.query(Subject).count() % len(SUBJECT_COLORS)]
    if not data["short"]:
        data["short"] = data["name"][:14]
    s = Subject(**data)
    db.add(s)
    db.commit()
    _replan_and_push(db)
    return to_dict(s)


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: int, payload: SubjectPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, Subject, subject_id, "Fach")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "exam_time" and v == "":
            v = None
        setattr(s, k, v)
    db.commit()
    _replan_and_push(db)
    return to_dict(s)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, Subject, subject_id, "Fach")
    for b in db.query(StudyBlock).filter(StudyBlock.subject_id == s.id).all():
        google_calendar.delete_remote_event(db, b.google_event_id)
        db.delete(b)
    for d in db.query(StudyDocument).filter(StudyDocument.subject_id == s.id).all():
        documents.delete_files(Path(d.stored_path))
    db.delete(s)
    db.commit()
    _replan_and_push(db)
    return {"ok": True}


@router.get("/subjects/{subject_id}")
def subject_detail(subject_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, Subject, subject_id, "Fach")
    progress = study_service.topic_progress(db)
    docs = db.query(StudyDocument).filter(StudyDocument.subject_id == s.id).order_by(StudyDocument.uploaded_at.desc()).all()
    planned: dict[int, int] = {}
    now = datetime.now()
    for b in db.query(StudyBlock).filter(StudyBlock.subject_id == s.id, StudyBlock.status == "geplant", StudyBlock.end >= now).all():
        if b.topic_id:
            planned[b.topic_id] = planned.get(b.topic_id, 0) + int((b.end - b.start).total_seconds() // 60)
    topics = []
    for t in s.topics:
        p = progress.get(t.id, {"done_minutes": 0, "reviews_done": 0})
        topics.append(
            {
                **to_dict(t),
                "done_minutes": p["done_minutes"],
                "reviews_done": p["reviews_done"],
                "planned_minutes": planned.get(t.id, 0),
            }
        )
    overview = next((o for o in study_service.subject_overview(db) if o["id"] == s.id), None)
    return {
        "subject": overview,
        "topics": topics,
        "documents": [to_dict(d, exclude={"stored_path"}) for d in docs],
        "claude_available": claude_ai.available(),
    }


# ---------------------------------------------------------------- Themen


class TopicIn(BaseModel):
    title: str = Field(min_length=1)
    effort_hours: float = Field(default=2.0, gt=0, le=100)
    difficulty: int = Field(default=2, ge=1, le=3)


class TopicsBulkIn(BaseModel):
    topics: list[TopicIn] | None = None
    text: str | None = None  # eine Zeile pro Thema, optional "Titel | Stunden | Schwierigkeit"
    replace: bool = False
    source: str = "manuell"


class TopicPatch(BaseModel):
    title: str | None = None
    effort_hours: float | None = Field(default=None, gt=0, le=100)
    difficulty: int | None = Field(default=None, ge=1, le=3)
    status: str | None = Field(default=None, pattern=r"^(offen|in_arbeit|fertig)$")
    order_index: int | None = None


def parse_topic_lines(text: str) -> list[TopicIn]:
    topics = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw).strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        title = parts[0]
        hours = 2.0
        diff = 2
        if len(parts) > 1:
            m = re.search(r"\d+(?:[.,]\d+)?", parts[1])
            if m:
                hours = float(m.group().replace(",", "."))
        if len(parts) > 2:
            m = re.search(r"[123]", parts[2])
            if m:
                diff = int(m.group())
        if title:
            topics.append(TopicIn(title=title[:250], effort_hours=max(0.25, hours), difficulty=diff))
    return topics


@router.post("/subjects/{subject_id}/topics")
def add_topics(subject_id: int, payload: TopicsBulkIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, Subject, subject_id, "Fach")
    items = list(payload.topics or [])
    if payload.text:
        items.extend(parse_topic_lines(payload.text))
    if not items:
        raise HTTPException(status_code=400, detail="Keine Themen angegeben.")
    if payload.replace:
        for t in list(s.topics):
            if t.status == "offen" and not study_service.topic_progress(db).get(t.id):
                db.delete(t)
        db.flush()
    start = max((t.order_index for t in s.topics), default=-1) + 1
    for i, item in enumerate(items):
        db.add(
            Topic(
                subject_id=s.id,
                title=item.title,
                effort_hours=item.effort_hours,
                difficulty=item.difficulty,
                order_index=start + i,
                source=payload.source if payload.source in ("manuell", "ki") else "manuell",
            )
        )
    db.commit()
    _replan_and_push(db)
    return {"added": len(items)}


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: TopicPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Topic, topic_id, "Thema")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    _replan_and_push(db)
    return to_dict(t)


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Topic, topic_id, "Thema")
    db.delete(t)
    db.commit()
    _replan_and_push(db)
    return {"ok": True}


class ReorderIn(BaseModel):
    topic_ids: list[int]


@router.post("/subjects/{subject_id}/reorder")
def reorder(subject_id: int, payload: ReorderIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Subject, subject_id, "Fach")
    for idx, tid in enumerate(payload.topic_ids):
        t = db.get(Topic, tid)
        if t and t.subject_id == subject_id:
            t.order_index = idx
    db.commit()
    _replan_and_push(db)
    return {"ok": True}


# ---------------------------------------------------------------- Unterlagen


@router.post("/subjects/{subject_id}/documents")
async def upload_documents(subject_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_or_404(db, Subject, subject_id, "Fach")
    saved, errors = [], []
    for f in files:
        data = await f.read()
        try:
            path = documents.store(s.id, f.filename or "datei", data)
            text = documents.cached_text(path)
        except documents.DocumentError as exc:
            errors.append(f"{f.filename}: {exc}")
            continue
        doc = StudyDocument(subject_id=s.id, filename=f.filename or path.name, stored_path=str(path), size=len(data), text_chars=len(text))
        db.add(doc)
        saved.append(doc)
    db.commit()
    return {"saved": [to_dict(d, exclude={"stored_path"}) for d in saved], "errors": errors}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = get_or_404(db, StudyDocument, doc_id, "Dokument")
    documents.delete_files(Path(d.stored_path))
    db.delete(d)
    db.commit()
    return {"ok": True}


class ExtractIn(BaseModel):
    document_ids: list[int] | None = None


@router.post("/subjects/{subject_id}/extract")
def extract(subject_id: int, payload: ExtractIn | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Schlägt mit Claude Themen aus den Unterlagen vor (werden erst nach Bestätigung gespeichert)."""
    s = get_or_404(db, Subject, subject_id, "Fach")
    q = db.query(StudyDocument).filter(StudyDocument.subject_id == s.id)
    if payload and payload.document_ids:
        q = q.filter(StudyDocument.id.in_(payload.document_ids))
    docs = q.order_by(StudyDocument.uploaded_at).all()
    if not docs:
        raise HTTPException(status_code=400, detail="Lade zuerst Unterlagen (PDF, Folien) für dieses Fach hoch.")
    texts = []
    for d in docs:
        try:
            texts.append((d.filename, documents.cached_text(Path(d.stored_path))))
        except (documents.DocumentError, FileNotFoundError) as exc:
            log.warning("Dokument %s nicht lesbar: %s", d.filename, exc)
            texts.append((d.filename, ""))
    try:
        result = claude_ai.extract_topics(s.name, texts, s.exam_date.strftime("%d.%m.%Y") if s.exam_date else None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=claude_ai.friendly_error(exc)) from exc
    for d in docs:
        d.topics_extracted = True
    db.commit()
    return result


# ---------------------------------------------------------------- Lernblöcke


class BlockStatusIn(BaseModel):
    status: str = Field(pattern=r"^(geplant|erledigt|verpasst)$")


@router.get("/blocks")
def blocks(start: str | None = None, end: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    s = parse_date(start, date.today() - timedelta(days=7))
    e = parse_date(end, date.today() + timedelta(days=28))
    rows = (
        db.query(StudyBlock)
        .filter(StudyBlock.start >= datetime.combine(s, datetime.min.time()), StudyBlock.start < datetime.combine(e + timedelta(days=1), datetime.min.time()))
        .order_by(StudyBlock.start)
        .all()
    )
    return [serialize_block(b) for b in rows]


@router.post("/blocks/{block_id}/status")
def set_block_status(block_id: int, payload: BlockStatusIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    b = get_or_404(db, StudyBlock, block_id, "Lernblock")
    b.status = payload.status
    db.commit()
    if b.topic:
        study_service.update_topic_status(db, b.topic)
        db.commit()
    result = _replan_and_push(db)
    return {"block": serialize_block(b), "replan": result}
