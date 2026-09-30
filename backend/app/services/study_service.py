"""Datenbank-Anbindung des Lernplans: Eingaben sammeln, neu planen, Fortschritt berechnen."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import (
    Activity,
    CalendarEvent,
    GoogleDeletion,
    PlannedWorkout,
    StudyBlock,
    Subject,
    Topic,
)
from . import agenda
from .study_planner import Busy, PlanSubject, PlannerConfig, PlanTopic, plan


def planner_config(db: Session) -> PlannerConfig:
    s = settings_store.get(db, "study")
    return PlannerConfig(
        day_start=agenda.parse_hhmm(s["day_start"]),
        day_end=agenda.parse_hhmm(s["day_end"]),
        max_minutes_per_day=int(s["max_minutes_per_day"]),
        block_minutes=int(s["block_minutes"]),
        min_block_minutes=int(s["min_block_minutes"]),
        break_minutes=int(s["break_minutes"]),
        buffer_days=int(s["buffer_days"]),
        review_intervals=tuple(int(x) for x in s["review_intervals"]),
        review_minutes=int(s["review_minutes"]),
        weekdays=frozenset(int(x) for x in s["weekdays"]),
        max_blocks_per_subject_per_day=int(s.get("max_blocks_per_subject_per_day", 3)),
    )


def plan_mode(db: Session) -> str:
    return "manuell" if settings_store.get(db, "study_plan_mode", "auto") == "manuell" else "auto"


def has_missed_auto_blocks(db: Session, now: datetime) -> bool:
    return (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end < now, StudyBlock.manual.is_(False))
        .first()
        is not None
    )


def mark_missed(db: Session, now: datetime) -> int:
    """Automatische Blöcke, die vorbei und nicht erledigt sind, gelten als verpasst.
    Selbst geplante Blöcke bleiben offen, bis du sie abhakst oder als verpasst markierst."""
    missed = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end < now, StudyBlock.manual.is_(False))
        .all()
    )
    for b in missed:
        b.status = "verpasst"
    if missed:
        db.commit()
    return len(missed)


def topic_progress(db: Session) -> dict[int, dict[str, Any]]:
    """Erledigte Lernminuten, Abschlussdatum und Wiederholungen je Thema."""
    data: dict[int, dict[str, Any]] = defaultdict(lambda: {"done_minutes": 0, "last_learn": None, "reviews_done": 0})
    for b in db.query(StudyBlock).filter(StudyBlock.status == "erledigt", StudyBlock.topic_id.isnot(None)).all():
        entry = data[b.topic_id]
        minutes = int((b.end - b.start).total_seconds() // 60)
        if b.kind == "lernen":
            entry["done_minutes"] += minutes
            if entry["last_learn"] is None or b.start.date() > entry["last_learn"]:
                entry["last_learn"] = b.start.date()
        elif b.kind == "wiederholung":
            entry["reviews_done"] += 1
    return data


def update_topic_status(db: Session, topic: Topic) -> None:
    prog = topic_progress(db).get(topic.id)
    done = prog["done_minutes"] if prog else 0
    if topic.status == "fertig" and done == 0:
        return  # manuell als fertig markiert
    if done >= topic.effort_hours * 60:
        topic.status = "fertig"
    elif done > 0:
        topic.status = "in_arbeit"


def collect_busy(db: Session, start: date, end: date, now: datetime) -> tuple[list[Busy], dict[date, int]]:
    cfg = settings_store.get(db, "study")
    pad = timedelta(minutes=int(cfg.get("event_padding_minutes", 15)))
    workout_pad = timedelta(minutes=int(cfg.get("workout_padding_minutes", 30)))
    busy: list[Busy] = []
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)

    for occ in agenda.timetable_occurrences(db, start, end):
        busy.append(Busy(occ["start"] - pad, occ["end"] + pad, occ["title"]))
    for ev in db.query(CalendarEvent).filter(CalendarEvent.start < end_dt, CalendarEvent.end > start_dt).all():
        if ev.all_day:
            continue
        busy.append(Busy(ev.start - pad, ev.end + pad, ev.title))
    for w in db.query(PlannedWorkout).filter(PlannedWorkout.date >= start, PlannedWorkout.date <= end).all():
        s = datetime.combine(w.date, agenda.parse_hhmm(w.start_time))
        busy.append(Busy(s - pad, s + timedelta(minutes=w.duration_min) + workout_pad, w.title))
    for a in db.query(Activity).filter(Activity.date >= start, Activity.date <= end).all():
        busy.append(Busy(a.start_time, a.start_time + timedelta(seconds=a.duration_s or 0) + workout_pad, a.name))

    used: dict[date, int] = defaultdict(int)
    kept = (
        db.query(StudyBlock)
        .filter(StudyBlock.start < end_dt, StudyBlock.end > start_dt)
        .filter(
            (StudyBlock.status == "erledigt")
            | ((StudyBlock.status == "geplant") & ((StudyBlock.start < now) | StudyBlock.manual.is_(True)))
        )
        .all()
    )
    for b in kept:
        busy.append(Busy(b.start, b.end, b.title))
        used[b.start.date()] += int((b.end - b.start).total_seconds() // 60)
    return busy, dict(used)


def manual_planned(db: Session, now: datetime) -> dict[int, dict[str, Any]]:
    """Minuten, die du selbst schon für ein Thema eingeplant hast (noch nicht erledigt),
    und der Tag des letzten dieser Blöcke."""
    out: dict[int, dict[str, Any]] = defaultdict(lambda: {"minutes": 0, "last": None})
    for b in (
        db.query(StudyBlock)
        .filter(
            StudyBlock.manual.is_(True),
            StudyBlock.status == "geplant",
            StudyBlock.kind == "lernen",
            StudyBlock.topic_id.isnot(None),
            StudyBlock.end >= now,
        )
        .all()
    ):
        entry = out[b.topic_id]
        entry["minutes"] += int((b.end - b.start).total_seconds() // 60)
        if entry["last"] is None or b.start.date() > entry["last"]:
            entry["last"] = b.start.date()
    return out


def build_subjects(db: Session, today: date, now: datetime | None = None) -> tuple[list[PlanSubject], list[str]]:
    progress = topic_progress(db)
    manual = manual_planned(db, now or datetime.combine(today, time.min))
    subjects: list[PlanSubject] = []
    notes: list[str] = []
    for s in db.query(Subject).filter(Subject.active.is_(True)).order_by(Subject.id).all():
        if not s.exam_date:
            if s.topics:
                notes.append(f"{s.name}: noch kein Prüfungstermin – wird nicht eingeplant.")
            continue
        if s.exam_date <= today:
            continue
        topics = []
        for t in s.topics:
            p = progress.get(t.id, {"done_minutes": 0, "last_learn": None, "reviews_done": 0})
            m = manual.get(t.id, {"minutes": 0, "last": None})
            if t.status == "fertig":
                remaining = 0
            else:
                remaining = max(0, int(round(t.effort_hours * 60)) - p["done_minutes"] - m["minutes"])
            learned_on = (m["last"] or p["last_learn"]) if remaining == 0 else None
            if remaining == 0 and learned_on is None:
                learned_on = today - timedelta(days=1)
            topics.append(PlanTopic(t.id, t.title, remaining, learned_on, p["reviews_done"], t.order_index))
        subjects.append(PlanSubject(s.id, s.name, s.exam_date, topics, label=s.short, study_start=s.study_start))
    return subjects, notes


def replan(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """Verpasste Blöcke markieren, zukünftige Blöcke verwerfen und neu verteilen."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    today = now.date()
    db.expire_all()  # frische Daten laden (Themen, die gerade hinzugefügt wurden)
    missed = mark_missed(db, now)

    # Zukünftige automatische Blöcke verwerfen (selbst geplante bleiben unangetastet);
    # ihre Google-Termine werden wiederverwendet statt gelöscht, damit der Kalender
    # beim Neuplanen nicht unnötig viele Termine löscht und neu anlegt.
    future = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.start >= now, StudyBlock.manual.is_(False))
        .all()
    )
    unchanged: dict[tuple, tuple[str, str | None]] = {}
    recycled: list[str] = []
    for b in sorted(future, key=lambda x: x.start):
        if b.google_event_id:
            key = (b.subject_id, b.topic_id, b.kind, b.review_number, b.start, b.end, b.title)
            if key not in unchanged:
                unchanged[key] = (b.google_event_id, b.google_hash)
            else:
                recycled.append(b.google_event_id)
        db.delete(b)
    db.flush()

    def release_event_ids() -> None:
        for event_id in recycled + [eid for eid, _ in unchanged.values()]:
            db.add(GoogleDeletion(google_event_id=event_id))

    if plan_mode(db) == "manuell":
        # Du planst selbst: keine automatischen Blöcke anlegen
        release_event_ids()
        db.commit()
        return {"created": 0, "missed": missed, "warnings": [], "unplanned": {}}

    subjects, notes = build_subjects(db, today, now)
    if not subjects:
        release_event_ids()
        db.commit()
        return {"created": 0, "missed": missed, "warnings": notes, "unplanned": {}}
    horizon_end = max(s.exam_date for s in subjects)
    busy, used = collect_busy(db, today, horizon_end, now)
    result = plan(subjects, busy, planner_config(db), now, used)

    is_demo = bool(settings_store.get(db, "demo_active", False))
    new_blocks = []
    for b in result.blocks:
        block = StudyBlock(
            subject_id=b.subject_id,
            topic_id=b.topic_id,
            start=b.start,
            end=b.end,
            kind=b.kind,
            review_number=b.review_number,
            status="geplant",
            title=b.title,
            is_demo=is_demo and db.get(Subject, b.subject_id).is_demo,
        )
        key = (b.subject_id, b.topic_id, b.kind, b.review_number, b.start, b.end, b.title)
        if key in unchanged:
            block.google_event_id, block.google_hash = unchanged.pop(key)
        new_blocks.append(block)
        db.add(block)
    # Übrige Termin-IDs an geänderte Blöcke vergeben (Termin wird dann aktualisiert)
    recycled.extend(eid for eid, _ in unchanged.values())
    unchanged.clear()
    for block in new_blocks:
        if not recycled:
            break
        if block.google_event_id is None:
            block.google_event_id = recycled.pop(0)
            block.google_hash = None
    release_event_ids()
    db.commit()
    return {
        "created": len(result.blocks),
        "missed": missed,
        "warnings": result.warnings + notes,
        "unplanned": result.unplanned_minutes,
    }


def subject_overview(db: Session, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    db.expire_all()
    progress = topic_progress(db)
    out = []
    now = datetime.now()
    for s in db.query(Subject).order_by(Subject.exam_date.is_(None), Subject.exam_date, Subject.name).all():
        required = sum(t.effort_hours * 60 for t in s.topics)
        done = 0.0
        for t in s.topics:
            if t.status == "fertig":
                done += t.effort_hours * 60
            else:
                done += min(progress.get(t.id, {}).get("done_minutes", 0), t.effort_hours * 60)
        blocks = db.query(StudyBlock).filter(StudyBlock.subject_id == s.id).all()
        planned_future = [b for b in blocks if b.status == "geplant" and b.end >= now]
        next_block = min(planned_future, key=lambda b: b.start, default=None)
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "short": s.short,
                "color": s.color,
                "exam_date": s.exam_date.isoformat() if s.exam_date else None,
                "exam_time": s.exam_time,
                "exam_location": s.exam_location,
                "study_start": s.study_start.isoformat() if s.study_start else None,
                "notes": s.notes,
                "active": s.active,
                "days_left": (s.exam_date - today).days if s.exam_date else None,
                "topics_total": len(s.topics),
                "topics_done": sum(1 for t in s.topics if t.status == "fertig"),
                "required_minutes": round(required),
                "done_minutes": round(done),
                "progress": round(done / required * 100) if required else 0,
                "planned_minutes": sum(int((b.end - b.start).total_seconds() // 60) for b in planned_future),
                "blocks_done": sum(1 for b in blocks if b.status == "erledigt"),
                "blocks_missed": sum(1 for b in blocks if b.status == "verpasst"),
                "next_block": next_block.start.isoformat() if next_block else None,
            }
        )
    return out


def serialize_block(b: StudyBlock) -> dict[str, Any]:
    return {
        "id": b.id,
        "subject_id": b.subject_id,
        "subject": b.subject.name if b.subject else "",
        "subject_short": b.subject.short if b.subject else "",
        "color": b.subject.color if b.subject else "#fb923c",
        "topic_id": b.topic_id,
        "topic": b.topic.title if b.topic else None,
        "start": b.start.isoformat(),
        "end": b.end.isoformat(),
        "minutes": int((b.end - b.start).total_seconds() // 60),
        "kind": b.kind,
        "review_number": b.review_number,
        "status": b.status,
        "title": b.title,
        "manual": bool(b.manual),
        "note": b.note or "",
        "synced": bool(b.google_event_id),
    }


# ---------------------------------------------------------------- Selbst geplante Blöcke


def default_block_title(subject: Subject, topic: Topic | None, kind: str) -> str:
    short = subject.short or subject.name
    if kind == "wiederholung":
        return f"{short}: Wiederholung {topic.title}" if topic else f"{short}: Wiederholung"
    if kind == "puffer":
        return f"Prüfungsvorbereitung {short}" + (f": {topic.title}" if topic else "")
    return f"{short}: {topic.title}" if topic else f"{short}: Lernen"


def conflicts(db: Session, start: datetime, end: datetime, exclude_block_id: int | None = None) -> list[str]:
    """Termine, die sich mit dem Zeitraum überschneiden (nur als Hinweis)."""
    out: list[str] = []
    q = db.query(StudyBlock).filter(StudyBlock.start < end, StudyBlock.end > start, StudyBlock.status != "verpasst")
    if exclude_block_id is not None:
        q = q.filter(StudyBlock.id != exclude_block_id)
    out += [f"Lernblock „{b.title}“" for b in q.all()]
    for ev in db.query(CalendarEvent).filter(CalendarEvent.start < end, CalendarEvent.end > start, CalendarEvent.all_day.is_(False)).all():
        out.append(f"Termin „{ev.title}“")
    for occ in agenda.timetable_occurrences(db, start.date(), end.date()):
        if occ["start"] < end and occ["end"] > start:
            out.append(f"Stundenplan „{occ['title']}“")
    return out


def convert_future_to_manual(db: Session, now: datetime | None = None) -> int:
    """Übernimmt den bisherigen automatischen Plan als eigenen Plan (nichts wird gelöscht)."""
    now = now or datetime.now()
    blocks = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end >= now, StudyBlock.manual.is_(False))
        .all()
    )
    for b in blocks:
        b.manual = True
    db.commit()
    return len(blocks)
