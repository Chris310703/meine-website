"""Anbindung an die Claude API (Anthropic). Ohne API-Schlüssel laufen alle anderen Funktionen weiter."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("lifeos.claude")

# Server-seitiger Fallback: lehnt das Modell eine Anfrage aus Sicherheitsgründen ab,
# beantwortet Anthropic sie automatisch mit einem passenden Ersatzmodell.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORT = os.getenv("CLAUDE_EFFORT", "medium").strip() or "medium"

_client = None


class ClaudeUnavailable(Exception):
    pass


class ClaudeError(Exception):
    pass


def available() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def client():
    global _client
    if not available():
        raise ClaudeUnavailable(
            "Kein Claude-API-Schlüssel hinterlegt. Trage ANTHROPIC_API_KEY in die .env ein (siehe README) und starte die App neu."
        )
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=180.0, max_retries=2)
    return _client


def _supports_fallbacks(model: str) -> bool:
    return model.startswith(("claude-opus-5", "claude-fable-5"))


def _request_kwargs(model: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"output_config": {"effort": EFFORT}}
    if _supports_fallbacks(model):
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return kwargs


def friendly_error(exc: Exception) -> str:
    import anthropic

    if isinstance(exc, (ClaudeUnavailable, ClaudeError)):
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "Der Claude-API-Schlüssel ist ungültig. Bitte ANTHROPIC_API_KEY in der .env prüfen."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "Der API-Schlüssel hat keine Berechtigung für dieses Modell."
    if isinstance(exc, anthropic.NotFoundError):
        return f"Das Modell „{config.CLAUDE_MODEL}“ wurde nicht gefunden. Bitte CLAUDE_MODEL in der .env prüfen."
    if isinstance(exc, anthropic.RateLimitError):
        return "Zu viele Anfragen an Claude – bitte kurz warten und erneut versuchen."
    if isinstance(exc, anthropic.BadRequestError):
        msg = getattr(exc, "message", str(exc))
        if "credit" in msg.lower() or "balance" in msg.lower():
            return "Dein Anthropic-Guthaben ist aufgebraucht. Bitte in der Anthropic Console aufladen."
        return f"Claude hat die Anfrage abgelehnt: {msg}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"Claude ist gerade nicht erreichbar (Fehler {exc.status_code}). Bitte später erneut versuchen."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Keine Verbindung zur Claude API – Internetverbindung prüfen."
    return f"Unerwarteter Fehler bei Claude: {exc}"


def _call(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Führt einen API-Aufruf aus; lehnt die API den Fallback-Parameter ab, ohne ihn wiederholen."""
    import anthropic

    try:
        return fn(**kwargs)
    except anthropic.BadRequestError as exc:
        if "fallbacks" in kwargs and "fallback" in str(exc).lower():
            log.info("Fallback-Parameter nicht unterstützt – wiederhole ohne.")
            kwargs.pop("fallbacks", None)
            kwargs.pop("betas", None)
            return fn(**kwargs)
        raise


def _check_stop(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise ClaudeError("Claude hat diese Anfrage abgelehnt. Bitte formuliere sie anders.")


# ---------------------------------------------------------------- Themen extrahieren


class ExtractedTopic(BaseModel):
    title: str = Field(description="Kurzer Thementitel, max. 80 Zeichen")
    effort_hours: float = Field(description="Geschätzter Lernaufwand in Stunden (1–12)")
    difficulty: int = Field(description="1 = leicht, 2 = mittel, 3 = schwer")
    summary: str = Field(description="Ein Satz, worum es geht")


class TopicList(BaseModel):
    topics: list[ExtractedTopic]


MAX_DOC_CHARS = 600_000  # ≈ 150.000 Tokens – bleibt weit unter dem Kontextfenster

EXTRACT_SYSTEM = (
    "Du bist ein erfahrener Lerncoach für Studierende der Rechts- und Wirtschaftswissenschaften. "
    "Du strukturierst Vorlesungsunterlagen in prüfungsrelevante Lernthemen und schätzt den Lernaufwand realistisch ein."
)


def extract_topics(subject: str, documents: list[tuple[str, str]], exam_date: str | None = None) -> dict[str, Any]:
    """documents: Liste aus (Dateiname, Text). Rückgabe: {"topics": [...], "note": str | None}."""
    c = client()
    parts = []
    used = 0
    skipped = []
    for name, text in documents:
        if not text.strip():
            skipped.append(f"{name} (kein lesbarer Text – evtl. eingescannt)")
            continue
        remaining = MAX_DOC_CHARS - used
        if remaining <= 0:
            skipped.append(f"{name} (Gesamtumfang zu groß)")
            continue
        chunk = text[:remaining]
        if len(chunk) < len(text):
            skipped.append(f"{name} (nur die ersten {len(chunk):,} Zeichen verwendet)".replace(",", "."))
        parts.append(f'<unterlage name="{name}">\n{chunk}\n</unterlage>')
        used += len(chunk)
    if not parts:
        raise ClaudeError("In den Unterlagen wurde kein lesbarer Text gefunden. Gib die Themen bitte manuell ein.")

    exam = f" Die Prüfung ist am {exam_date}." if exam_date else ""
    prompt = (
        f"Fach: {subject}.{exam}\n\n"
        + "\n\n".join(parts)
        + "\n\nErstelle daraus eine Liste von 5 bis 25 Lernthemen in einer sinnvollen Lernreihenfolge "
        "(Grundlagen zuerst). Fasse Kleinigkeiten zusammen, damit jedes Thema 1–12 Stunden Lernaufwand hat "
        "(inklusive Übungsfälle bzw. Rechenaufgaben). Schätze die Schwierigkeit (1 leicht, 2 mittel, 3 schwer). "
        "Schreibe Titel und Zusammenfassung auf Deutsch."
    )
    model = config.CLAUDE_MODEL
    response = _call(
        c.beta.messages.parse,
        model=model,
        max_tokens=16000,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=TopicList,
        **_request_kwargs(model),
    )
    _check_stop(response)
    parsed: TopicList | None = response.parsed_output
    if parsed is None:
        raise ClaudeError("Claude hat keine auswertbare Themenliste geliefert. Bitte erneut versuchen.")
    topics = []
    for t in parsed.topics:
        topics.append(
            {
                "title": t.title.strip()[:250],
                "effort_hours": round(min(max(float(t.effort_hours), 0.5), 20), 1),
                "difficulty": min(max(int(t.difficulty), 1), 3),
                "summary": t.summary.strip(),
            }
        )
    note = ("Hinweis: " + "; ".join(skipped)) if skipped else None
    return {"topics": topics, "note": note}


# ---------------------------------------------------------------- Chat mit Werkzeugen


def run_with_tools(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute: Callable[[str, dict[str, Any]], Any],
    max_rounds: int = 8,
) -> dict[str, Any]:
    """Agentische Schleife: Claude ruft App-Werkzeuge auf, bis die Antwort fertig ist."""
    c = client()
    model = config.CLAUDE_MODEL
    convo = list(messages)
    used_tools: list[str] = []
    for _ in range(max_rounds):
        response = _call(
            c.beta.messages.create,
            model=model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=convo,
            **_request_kwargs(model),
        )
        _check_stop(response)
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_calls:
            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason == "max_tokens":
                text += "\n\n_(Antwort wurde wegen Längenbegrenzung abgeschnitten.)_"
            return {"text": text or "(keine Antwort)", "tools": used_tools}
        convo.append({"role": "assistant", "content": response.content})
        results = []
        for call in tool_calls:
            used_tools.append(call.name)
            try:
                output = execute(call.name, dict(call.input or {}))
                content = json.dumps(output, ensure_ascii=False, default=str)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": content})
            except Exception as exc:  # Werkzeugfehler an Claude zurückgeben
                log.exception("Werkzeug %s fehlgeschlagen", call.name)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": f"Fehler: {exc}", "is_error": True})
        convo.append({"role": "user", "content": results})
    return {"text": "Ich konnte die Frage nicht in wenigen Schritten beantworten – bitte formuliere sie etwas konkreter.", "tools": used_tools}


def simple_completion(system: str, prompt: str, max_tokens: int = 4000) -> str:
    c = client()
    model = config.CLAUDE_MODEL
    response = _call(
        c.beta.messages.create,
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        **_request_kwargs(model),
    )
    _check_stop(response)
    return "\n".join(b.text for b in response.content if b.type == "text").strip()
