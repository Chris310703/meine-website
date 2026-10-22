"""KI-Reiter: Chat mit Claude und Zugriff auf die App-Daten."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal, get_db
from ..models import ChatMessage
from ..services import ai_tools, claude_ai
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["KI"])

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
