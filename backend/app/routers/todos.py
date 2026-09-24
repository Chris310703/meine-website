"""To-dos mit Priorität, Fälligkeit und Fach bzw. Kategorie."""

from __future__ import annotations

from datetime import date, datetime
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..database import get_db
from ..models import Subject, Todo
from ..utils import get_or_404, to_dict
from .core import todo_sort_key

router = APIRouter(prefix="/api/todos", tags=["To-dos"])

PRIO = r"^(hoch|mittel|niedrig)$"


class TodoIn(BaseModel):
    title: str = Field(min_length=1)
    notes: str = ""
    priority: str = Field(default="mittel", pattern=PRIO)
    due_date: Date | None = None
    category: str = ""
    subject_id: int | None = None


class TodoPatch(BaseModel):
    title: str | None = None
    notes: str | None = None
    priority: str | None = Field(default=None, pattern=PRIO)
    due_date: Date | None = None
    category: str | None = None
    subject_id: int | None = None
    done: bool | None = None


def serialize(t: Todo, today: date) -> dict[str, Any]:
    d = to_dict(t)
    d["subject"] = t.subject.name if t.subject else None
    d["subject_short"] = t.subject.short if t.subject else None
    d["subject_color"] = t.subject.color if t.subject else None
    d["overdue"] = bool(not t.done and t.due_date and t.due_date < today)
    return d


@router.get("")
def todos(status: str = "offen", db: Session = Depends(get_db)) -> dict[str, Any]:
    today = date.today()
    q = db.query(Todo)
    if status == "offen":
        q = q.filter(Todo.done.is_(False))
    elif status == "erledigt":
        q = q.filter(Todo.done.is_(True))
    rows = q.all()
    if status == "erledigt":
        rows.sort(key=lambda t: t.done_at or datetime.min, reverse=True)
    else:
        rows.sort(key=lambda t: (t.done, todo_sort_key(t, today)))
    open_rows = db.query(Todo).filter(Todo.done.is_(False)).all()
    return {
        "todos": [serialize(t, today) for t in rows],
        "counts": {
            "offen": len(open_rows),
            "ueberfaellig": sum(1 for t in open_rows if t.due_date and t.due_date < today),
            "heute": sum(1 for t in open_rows if t.due_date == today),
            "hoch": sum(1 for t in open_rows if t.priority == "hoch"),
            "erledigt": db.query(Todo).filter(Todo.done.is_(True)).count(),
        },
        "categories": settings_store.get(db, "todo_categories"),
        "subjects": [{"id": s.id, "name": s.name, "short": s.short, "color": s.color} for s in db.query(Subject).order_by(Subject.name).all()],
    }


@router.post("")
def create(payload: TodoIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = Todo(**payload.model_dump())
    db.add(t)
    db.commit()
    return serialize(t, date.today())


@router.patch("/{todo_id}")
def update(todo_id: int, payload: TodoPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Todo, todo_id, "Aufgabe")
    data = payload.model_dump(exclude_unset=True)
    if "done" in data:
        t.done_at = datetime.now().replace(microsecond=0) if data["done"] else None
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    return serialize(t, date.today())


@router.delete("/{todo_id}")
def delete(todo_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Todo, todo_id, "Aufgabe")
    db.delete(t)
    db.commit()
    return {"ok": True}
