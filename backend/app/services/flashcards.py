"""Karteikarten: Spaced Repetition (SM-2-Variante) und Import aus Claude-Text/JSON.

Bewertung pro Karte (wie bei Anki):
  1 = Nochmal (falsch)  → kommt in 10 Minuten wieder, Abstand beginnt von vorn
  2 = Schwer            → richtig, aber kleiner Abstand
  3 = Gut               → richtig, normaler Abstand
  4 = Leicht            → richtig, großer Abstand
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

MIN_EASE = 1.3
MAX_INTERVAL = 365
RELEARN_MINUTES = 10

GRADES = {1: "Nochmal", 2: "Schwer", 3: "Gut", 4: "Leicht"}


@dataclass
class SrsState:
    ease: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


def next_interval(state: SrsState, grade: int) -> int:
    """Neuer Abstand in Tagen (0 = gleich noch einmal)."""
    if grade == 1:
        return 0
    reps, ivl, ease = state.repetitions, max(state.interval_days, 1), state.ease
    if grade == 2:
        days = 1 if reps == 0 else max(ivl + 1, round(ivl * 1.2))
    elif grade == 3:
        days = 1 if reps == 0 else 3 if reps == 1 else max(ivl + 1, round(ivl * ease))
    else:
        good = 1 if reps == 0 else 3 if reps == 1 else max(ivl + 1, round(ivl * ease))
        days = max(4, good + 1, round(good * 1.3))
    return min(days, MAX_INTERVAL)


def schedule(state: SrsState, grade: int, now: datetime) -> tuple[SrsState, datetime]:
    """Wendet eine Bewertung an. Rückgabe: neuer Zustand und nächster Fälligkeitszeitpunkt."""
    if grade not in GRADES:
        raise ValueError("Bewertung muss 1–4 sein.")
    days = next_interval(state, grade)
    if grade == 1:
        new = SrsState(max(MIN_EASE, state.ease - 0.2), 0, 0, state.lapses + (1 if state.repetitions else 0))
        return new, now + timedelta(minutes=RELEARN_MINUTES)
    ease = state.ease + {2: -0.15, 3: 0.0, 4: 0.15}[grade]
    new = SrsState(round(max(MIN_EASE, ease), 2), days, state.repetitions + 1, state.lapses)
    # Fällig ab Beginn des Tages – so kann man morgens alles für den Tag erledigen
    return new, datetime.combine((now + timedelta(days=days)).date(), time.min)


def interval_label(days: int) -> str:
    if days <= 0:
        return f"{RELEARN_MINUTES} min"
    if days < 30:
        return f"{days} T"
    if days < 365:
        return f"{round(days / 30.4, 1):g} Mon".replace(".", ",")
    return f"{round(days / 365, 1):g} J".replace(".", ",")


def preview(state: SrsState) -> dict[int, str]:
    """Beschriftung der vier Knöpfe: wann kommt die Karte wieder?"""
    return {g: interval_label(next_interval(state, g)) for g in GRADES}


# ---------------------------------------------------------------- Import

FRONT_KEYS = ("frage", "vorderseite", "front", "question", "q", "begriff", "vorne")
BACK_KEYS = ("antwort", "rückseite", "rueckseite", "back", "answer", "a", "erklärung", "definition", "hinten")
SUBJECT_KEYS = ("fach", "subject", "deck", "kurs", "modul")
TOPIC_KEYS = ("thema", "topic", "kapitel", "chapter", "unterthema")
CARDS_KEYS = ("karten", "karteikarten", "cards", "flashcards")

Q_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:F|Frage|Q|Question|Vorderseite|Vorne)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$", re.I)
A_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:A|Antwort|Answer|Rückseite|Rueckseite|Hinten)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$", re.I)
SUBJECT_RE = re.compile(r"^\s*#{1,6}\s*(?:Fach|Subject|Deck|Modul)\s*[:\-–]\s*(.+)$", re.I)
TOPIC_RE = re.compile(r"^\s*#{1,6}\s*(?:Thema|Topic|Kapitel)\s*[:\-–]\s*(.+)$", re.I)
PLAIN_SUBJECT_RE = re.compile(r"^\s*(?:Fach|Subject|Deck|Modul)\s*:\s*(.+)$", re.I)
PLAIN_TOPIC_RE = re.compile(r"^\s*(?:Thema|Topic|Kapitel)\s*:\s*(.+)$", re.I)
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")


def _pick(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower = {str(k).strip().lower(): v for k, v in d.items()}
    for k in keys:
        if k in lower and lower[k] not in (None, ""):
            return lower[k]
    return None


def _clean(text: Any) -> str:
    if isinstance(text, list):
        text = "\n".join(f"• {x}" for x in text)
    return str(text or "").strip()


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json|text|txt|csv|markdown|md)?\s*\n(.*?)```", text, re.S | re.I)
    return m.group(1) if m else text


def _from_json(data: Any, subject: str | None = None, topic: str | None = None) -> list[dict[str, str | None]]:
    out: list[dict[str, str | None]] = []
    if isinstance(data, list):
        for item in data:
            out.extend(_from_json(item, subject, topic))
        return out
    if not isinstance(data, dict):
        return out
    subject = _clean(_pick(data, SUBJECT_KEYS)) or subject
    topic = _clean(_pick(data, TOPIC_KEYS)) or topic
    front, back = _pick(data, FRONT_KEYS), _pick(data, BACK_KEYS)
    if front is not None and back is not None:
        out.append({"subject": subject, "topic": topic, "front": _clean(front), "back": _clean(back)})
    for key in (*CARDS_KEYS, "themen", "topics", "kapitel", "fächer", "faecher", "subjects"):
        children = next((v for k, v in data.items() if str(k).lower() == key), None)
        if isinstance(children, list):
            out.extend(_from_json(children, subject, topic))
    return out


def _split_line(line: str) -> tuple[str, str] | None:
    raw = line.strip()
    if raw.startswith("|") and raw.endswith("|") and raw.count("|") >= 3:  # Markdown-Tabelle
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[1]:
            return cells[0], cells[1]
        return None
    for sep in ("\t", " | ", "|", " :: ", ";"):
        if sep in raw:
            front, back = raw.split(sep, 1)
            if front.strip() and back.strip():
                return front.strip(), back.strip()
    return None


def _from_text(text: str) -> list[dict[str, str | None]]:
    out: list[dict[str, str | None]] = []
    subject: str | None = None
    topic: str | None = None
    q: list[str] | None = None
    a: list[str] | None = None
    header_skipped = False

    def flush() -> None:
        nonlocal q, a
        if q is not None and a is not None:
            front, back = "\n".join(q).strip(), "\n".join(a).strip()
            if front and back:
                out.append({"subject": subject, "topic": topic, "front": front, "back": back})
        q = a = None

    for line in text.splitlines():
        if m := (SUBJECT_RE.match(line) or PLAIN_SUBJECT_RE.match(line)):
            flush()
            subject, topic = m.group(1).strip().strip("*"), None
            continue
        if m := (TOPIC_RE.match(line) or PLAIN_TOPIC_RE.match(line)):
            flush()
            topic = m.group(1).strip().strip("*")
            continue
        if m := Q_RE.match(line):
            flush()
            q = [m.group(1).strip().rstrip("*").strip()]
            continue
        if m := A_RE.match(line):
            if q is not None:
                a = [m.group(1).strip().rstrip("*").strip()]
            continue
        if a is not None:  # mehrzeilige Antwort
            if line.strip():
                a.append(line.rstrip())
            continue
        if q is not None:  # mehrzeilige Frage
            if line.strip():
                q.append(line.rstrip())
            continue
        if not line.strip() or TABLE_SEP_RE.match(line):
            continue
        pair = _split_line(line)
        if pair:
            if not header_skipped and pair[0].lower() in FRONT_KEYS and pair[1].lower() in BACK_KEYS:
                header_skipped = True
                continue
            out.append({"subject": subject, "topic": topic, "front": pair[0], "back": pair[1]})
    flush()
    return out


def parse_import(text: str) -> list[dict[str, str | None]]:
    """Erkennt JSON, „F:/A:“-Blöcke, Tabellen und Zeilen „Frage | Antwort“ (auch Tab oder ;).

    Rückgabe: Liste aus {"subject", "topic", "front", "back"} – subject/topic sind None,
    wenn der Text sie nicht angibt (dann gilt die Auswahl im Import-Dialog).
    """
    body = _strip_fences(text or "").strip()
    if body[:1] in "[{":
        try:
            return [c for c in _from_json(json.loads(body)) if c["front"] and c["back"]]
        except json.JSONDecodeError:
            pass
    return _from_text(body)


CLAUDE_PROMPT = """Erstelle Karteikarten zum folgenden Stoff.
Antworte NUR mit einem JSON-Codeblock in genau diesem Format:

```json
{
  "fach": "Name des Fachs",
  "themen": [
    {
      "thema": "Name des Themas",
      "karten": [
        {"frage": "…", "antwort": "…"}
      ]
    }
  ]
}
```

Regeln:
- Eine Karte = eine Frage mit einer kurzen, präzisen Antwort (lieber mehr kleine Karten).
- Fachbegriffe, Definitionen, Voraussetzungen/Prüfungsschemata, Paragraphen und typische Klausurfragen abdecken.
- Aufzählungen in der Antwort mit Zeilenumbrüchen (\\n) trennen.
- Sprache: Deutsch.

Stoff:
"""
