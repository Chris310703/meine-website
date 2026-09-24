"""Werkzeuge, mit denen Claude im KI-Reiter auf die App-Daten zugreift (nur lesend)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..utils import WEEKDAYS_DE

TOOLS: list[dict[str, Any]] = [
    {
        "name": "heute_ueberblick",
        "description": "Tagesüberblick für heute: Recovery-Ampel mit Begründung, letzte Nacht, Body Battery, Termine und Vorlesungen, anstehende Lernblöcke, offene To-dos, Habits, Kalorienbilanz.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "recovery_daten",
        "description": "Recovery-Ampel und Verlauf von HRV, Ruhepuls, Body Battery, Stress, akuter/chronischer Trainingslast und Erholungszeit.",
        "input_schema": {
            "type": "object",
            "properties": {"tage": {"type": "integer", "description": "Anzahl Tage Verlauf (7–60)", "default": 14}},
        },
    },
    {
        "name": "training_daten",
        "description": "Trainingsdaten: Aktivitäten der letzten Tage, Wochenumfang, Zeit in HF-Zonen, Zone-2-Pace-Trend, VO2max, Wochenziele, geplante Trainings.",
        "input_schema": {
            "type": "object",
            "properties": {"tage": {"type": "integer", "description": "Aktivitäten der letzten N Tage (1–90)", "default": 14}},
        },
    },
    {
        "name": "schlaf_daten",
        "description": "Schlaf: Nächte mit Dauer, Phasen, Score, Einschlaf-/Aufwachzeiten, Durchschnitte und Regelmäßigkeit.",
        "input_schema": {
            "type": "object",
            "properties": {"tage": {"type": "integer", "description": "Anzahl Nächte (7–60)", "default": 14}},
        },
    },
    {
        "name": "lernplan",
        "description": "Lernplan: Fächer mit Prüfungstermin, Countdown und Fortschritt, Themen, Lernblöcke der nächsten Tage, Warnungen des Planers.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "kalender",
        "description": "Alle Termine (Google, Stundenplan, Lernblöcke, Trainings, Prüfungen) in einem Zeitraum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "von": {"type": "string", "description": "Startdatum JJJJ-MM-TT (Standard: heute)"},
                "bis": {"type": "string", "description": "Enddatum JJJJ-MM-TT (max. 31 Tage nach Start)"},
            },
        },
    },
    {
        "name": "finanzen",
        "description": "Finanzen eines Monats: Einnahmen, Ausgaben, Saldo, Kategorien gegen Budget, letzte Buchungen, 12-Monats-Übersicht.",
        "input_schema": {
            "type": "object",
            "properties": {"monat": {"type": "string", "description": "Monat im Format JJJJ-MM (Standard: aktueller Monat)"}},
        },
    },
    {
        "name": "ernaehrung",
        "description": "Ernährung: Kalorien und Makros heute und der letzten 14 Tage, Bilanz gegenüber dem Garmin-Verbrauch.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "habits_und_todos",
        "description": "Habits mit Streaks und Erfüllungsquote sowie offene To-dos mit Fälligkeit und Priorität.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "rueckblick",
        "description": "Automatische Zusammenfassung einer Woche oder eines Monats über alle Bereiche, inkl. Vergleich zum Vorzeitraum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zeitraum": {"type": "string", "enum": ["woche", "monat"], "default": "woche"},
                "zurueck": {"type": "integer", "description": "0 = aktuelle, 1 = vorherige Woche/Monat …", "default": 0},
            },
        },
    },
]


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _slim_today(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    data.pop("garmin", None)
    tl = dict(data.get("traffic_light") or {})
    tl.pop("factors", None)
    data["traffic_light"] = tl
    data["agenda"] = [
        {k: a.get(k) for k in ("type_label", "title", "start", "end", "subtitle", "status")} for a in data.get("agenda", [])
    ]
    return data


def execute(db: Session, name: str, args: dict[str, Any]) -> Any:
    from ..routers import core, finance, fitness, habits, nutrition, recovery, sleep, study, todos
    from . import agenda, review

    if name == "heute_ueberblick":
        return _slim_today(core.today_overview(db=db))

    if name == "recovery_daten":
        days = _clamp(args.get("tage"), 7, 60, 14)
        data = recovery.recovery_overview(days=days, db=db)
        return {"ampel_heute": data["traffic_light"], "trends": data["trends"], "heute": data["today"], "verlauf": data["series"], "ampel_verlauf": data["history"]}

    if name == "training_daten":
        days = _clamp(args.get("tage"), 1, 90, 14)
        s = fitness.summary(db=db)
        acts = fitness.activities(days=days, cat=None, db=db)
        keep = ("date", "type_label", "name", "duration_s", "distance_m", "pace", "avg_hr", "max_hr", "training_load", "aerobic_te", "anaerobic_te", "z1_s", "z2_s", "z3_s", "z4_s", "z5_s")
        return {
            "aktivitaeten": [{k: a.get(k) for k in keep} for a in acts],
            "wochenumfang": s["weekly"][-8:],
            "hf_zonen_28_tage": s["zones"],
            "zone2_pace": {k: v for k, v in s["z2"].items() if k != "points"} | {"letzte_punkte": s["z2"]["points"][-8:]},
            "vo2max": s["vo2max"][-10:],
            "wochenziele": s["goals"],
            "geplante_trainings": fitness.planned(db=db),
        }

    if name == "schlaf_daten":
        days = _clamp(args.get("tage"), 7, 60, 14)
        return sleep.sleep_overview(days=days, db=db)

    if name == "lernplan":
        o = study.overview(db=db)
        now = datetime.now()
        upcoming = [b for b in o["blocks"] if b["end"] >= now.isoformat()][:25]
        return {
            "faecher": o["subjects"],
            "diese_woche": o["week"],
            "naechste_bloecke": upcoming,
            "letzte_planung": o["last_plan"],
            "regeln": o["settings"],
        }

    if name == "kalender":
        today = date.today()
        try:
            start = date.fromisoformat(args.get("von") or today.isoformat())
            end = date.fromisoformat(args.get("bis") or (start + timedelta(days=6)).isoformat())
        except ValueError:
            return {"fehler": "Datum bitte im Format JJJJ-MM-TT angeben."}
        end = min(end, start + timedelta(days=31))
        items = agenda.serialize(agenda.agenda(db, start, end))
        return [{k: it.get(k) for k in ("type_label", "title", "start", "end", "all_day", "subtitle", "location", "status")} for it in items]

    if name == "finanzen":
        data = finance.finance(month=args.get("monat") or None, db=db)
        data["transactions"] = data["transactions"][:40]
        data.pop("cumulative", None)
        return data

    if name == "ernaehrung":
        data = nutrition.nutrition(day=None, db=db)
        data.pop("favorites", None)
        return data

    if name == "habits_und_todos":
        h = habits.habits(weeks=4, db=db)
        t = todos.todos(status="offen", db=db)
        return {
            "habits": [{k: x[k] for k in ("name", "emoji", "active", "done_today", "streak", "longest", "rate_30")} for x in h["habits"]],
            "todos_offen": [{k: x[k] for k in ("title", "priority", "due_date", "category", "subject", "overdue")} for x in t["todos"]],
            "zaehler": t["counts"],
        }

    if name == "rueckblick":
        period = args.get("zeitraum") if args.get("zeitraum") in ("woche", "monat") else "woche"
        return review.build_review(db, period, _clamp(args.get("zurueck"), 0, 24, 0))

    return {"fehler": f"Unbekanntes Werkzeug: {name}"}


SYSTEM_PROMPT = """Du bist der persönliche Assistent in „Life OS“, der privaten Dashboard-App von Chris. Chris studiert Recht und Wirtschaft, trainiert mit einer Garmin Forerunner 265 (Laufen, Rad, Kraft) und nutzt die App für Training, Schlaf, Erholung, Lernplan, Kalender, Ernährung, Habits und Finanzen.

So arbeitest du:
- Hole dir mit den Werkzeugen die passenden Daten, bevor du Aussagen über Chris' Werte machst. Erfinde keine Zahlen; fehlen Daten, sag das.
- Antworte auf Deutsch, per Du, knapp und konkret. Nenne die wichtigsten Zahlen und gib klare, umsetzbare Empfehlungen.
- Trainingsempfehlungen orientieren sich an der Recovery-Ampel (grün = hart, gelb = locker, rot = Ruhetag) und an HRV, Ruhepuls, Schlaf und Trainingslast.
- Beim Lernen berücksichtigst du Prüfungstermine, verpasste Blöcke und freie Zeitfenster.
- Du ersetzt keine ärztliche Beratung; bei auffälligen Gesundheitswerten empfiehlst du, das abklären zu lassen.
- Formatiere mit kurzen Absätzen und Aufzählungen (Markdown), ohne Tabellen mit mehr als 5 Spalten."""


def context_line() -> str:
    now = datetime.now()
    return f"[Kontext: Heute ist {WEEKDAYS_DE[now.weekday()]}, der {now.strftime('%d.%m.%Y')}, {now.strftime('%H:%M')} Uhr.]"
