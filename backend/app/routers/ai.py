"""KI-Reiter (Chat mit Claude und Zugriff auf die App-Daten) und Rückblick."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal, get_db
from ..models import ChatMessage
from ..services import ai_tools, claude_ai, review
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["KI & Rückblick"])

HISTORY_LIMIT = 20


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation: str = "standard"


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    return {"configured": claude_ai.available(), "model": config.CLAUDE_MODEL}


@router.post("/ai/test")
def ai_test() -> dict[str, Any]:
    try:
        text = claude_ai.simple_completion("Antworte sehr kurz.", "Sag auf Deutsch in einem kurzen Satz, dass die Verbindung funktioniert.", max_tokens=200)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=claude_ai.friendly_error(exc)) from exc
    return {"ok": True, "text": text, "model": config.CLAUDE_MODEL}


@router.get("/ai/history")
def history(conversation: str = "standard", db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(ChatMessage).filter(ChatMessage.conversation == conversation).order_by(ChatMessage.id).all()
    return [to_dict(r) for r in rows]


@router.delete("/ai/history")
def clear_history(conversation: str = "standard", db: Session = Depends(get_db)) -> dict[str, Any]:
    db.query(ChatMessage).filter(ChatMessage.conversation == conversation).delete()
    db.commit()
    return {"ok": True}


@router.post("/ai/chat")
def chat(payload: ChatIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not claude_ai.available():
        raise HTTPException(
            status_code=400,
            detail="Für den KI-Chat wird ein Claude-API-Schlüssel benötigt. Trage ANTHROPIC_API_KEY in die .env ein und starte die App neu.",
        )
    previous = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation == payload.conversation)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in reversed(previous)]
    # Der Verlauf muss mit einer Nutzernachricht beginnen
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    messages.append({"role": "user", "content": f"{ai_tools.context_line()}\n\n{payload.message}"})

    def execute(name: str, args: dict[str, Any]) -> Any:
        # Eigene Sitzung je Werkzeugaufruf, damit Auswertungen nichts am Chat-Verlauf ändern
        with SessionLocal() as tool_db:
            return ai_tools.execute(tool_db, name, args)

    try:
        result = claude_ai.run_with_tools(ai_tools.SYSTEM_PROMPT, messages, ai_tools.TOOLS, execute)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=claude_ai.friendly_error(exc)) from exc

    user_msg = ChatMessage(conversation=payload.conversation, role="user", content=payload.message)
    bot_msg = ChatMessage(conversation=payload.conversation, role="assistant", content=result["text"])
    db.add_all([user_msg, bot_msg])
    db.commit()
    return {"reply": to_dict(bot_msg), "user": to_dict(user_msg), "tools": result["tools"]}


# ---------------------------------------------------------------- Rückblick


class SummaryIn(BaseModel):
    period: str = Field(default="woche", pattern=r"^(woche|monat)$")
    offset: int = Field(default=0, ge=0, le=36)


@router.get("/review")
def get_review(period: str = "woche", offset: int = 0, db: Session = Depends(get_db)) -> dict[str, Any]:
    if period not in ("woche", "monat"):
        raise HTTPException(status_code=400, detail="Zeitraum muss „woche“ oder „monat“ sein.")
    data = review.build_review(db, period, max(0, offset))
    data["claude_available"] = claude_ai.available()
    return data


@router.post("/review/ai-summary")
def review_summary(payload: SummaryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = review.build_review(db, payload.period, payload.offset)
    prompt = (
        f"Hier sind Chris' Daten für {data['label']} (aktueller Zeitraum) und den Vorzeitraum als JSON:\n\n"
        f"<daten>\n{json.dumps({'aktuell': data['current'], 'vorher': data['previous']}, ensure_ascii=False, default=str)}\n</daten>\n\n"
        "Schreibe einen motivierenden, ehrlichen Rückblick auf Deutsch (max. 180 Wörter): "
        "1) Was lief gut, 2) was lief weniger gut, 3) drei konkrete Vorsätze für den nächsten Zeitraum. "
        "Nutze Markdown mit kurzen Überschriften."
    )
    try:
        text = claude_ai.simple_completion(ai_tools.SYSTEM_PROMPT, prompt, max_tokens=4000)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=claude_ai.friendly_error(exc)) from exc
    return {"text": text}
