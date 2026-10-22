"""Trainingsplan: Standardplan für Chris, letzte Leistungen und Progressionsvorschläge."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import PlanExercise, TrainingSession, WorkoutLog, WorkoutSet

KIND_LABELS = {
    "kraft": "Krafttraining",
    "praevention": "Athletik & Prävention",
    "fussball": "Fußball",
    "handball": "Handball",
    "lauf": "Laufen",
    "ruhe": "Ruhetag",
    "sonstiges": "Sonstiges",
}

GUIDE: dict[str, Any] = {
    "goal": "Hybrid: Kraft und Muskulatur aufbauen – Ausdauer, Spritzigkeit und Sprints holst du dir beim Fußball (Di, Do, So) und Handball.",
    "rules": [
        "Doppelte Progression: Schaffst du in allen Sätzen die obere Wiederholungszahl sauber, erhöhst du beim nächsten Mal das Gewicht (Langhantel +2,5 kg, Kurzhanteln +1–2 kg). Sonst gleiches Gewicht und eine Wiederholung mehr anpeilen.",
        "Intensität: 1–2 Wiederholungen „im Tank“ lassen (RPE 8). Vor dem Fußball und am Tag vor dem Spiel nie bis zum Muskelversagen.",
        "Aufwärmen: 5–8 min Seilspringen oder Mobility, dann 2 leichte Aufwärmsätze bei der ersten Übung.",
        "Alle 6 Wochen eine leichtere Woche (Deload): Gewichte etwa −20 %, nur die Hälfte der Sätze.",
        "Recovery-Ampel rot oder sehr schlechter Schlaf: Krafteinheit nur locker machen oder ausfallen lassen.",
        "Ernährung: ca. 1,6–2 g Eiweiß pro kg Körpergewicht und genug Kohlenhydrate an Fußballtagen.",
    ],
}

# Wochenplan: Fußball Di/Do/So, Ruhetage Mi/Fr, manchmal Handball am Montag.
DEFAULT_PLAN: list[dict[str, Any]] = [
    {
        "weekday": 0,
        "kind": "kraft",
        "title": "Oberkörper A – Drücken",
        "duration_min": 60,
        "notes": "Nach dem Spiel am Sonntag erholen sich die Beine, deshalb heute Oberkörper. Hast du abends Handball, trainiere vorher (mind. 3 h Abstand) oder mach nur die ersten 4 Übungen. Kein Handball? Optional danach 20–30 min lockerer Lauf (Zone 2).",
        "exercises": [
            ("Bankdrücken (Langhantel)", 4, "6–8", 150, 2.5, "Schulterblätter zusammen und nach unten, Füße fest am Boden, Stange kontrolliert zur unteren Brust.", "Ohne Bank: Bodendrücken (Floor Press)"),
            ("Klimmzüge (Obergriff)", 4, "6–10", 120, 2.5, "Unten ganz strecken, Brust zur Stange ziehen. Schaffst du 4 × 10, mit Zusatzgewicht (Kurzhantel zwischen den Füßen) – eingetragen wird das Zusatzgewicht.", "Negative Klimmzüge: hochspringen, 5 s ablassen"),
            ("Schulterdrücken stehend (Langhantel)", 3, "6–8", 120, 2.5, "Gesäß und Bauch fest anspannen, kein Hohlkreuz, Kopf am Ende leicht nach vorne „durch das Fenster“.", "Kurzhantel-Schulterdrücken"),
            ("Einarmiges Kurzhantelrudern", 3, "8–12", 90, 2.0, "Je Seite. Rücken gerade, Ellbogen nah am Körper Richtung Hüfte ziehen.", ""),
            ("Schrägbankdrücken (Kurzhanteln)", 3, "8–12", 90, 2.0, "Bank auf ca. 30°, Hanteln oben nicht zusammenschlagen.", "Ohne Schrägbank: Kurzhantel-Bodendrücken"),
            ("Seitheben (Kurzhanteln)", 3, "12–15", 60, 1.0, "Leichtes Gewicht, Arme leicht gebeugt, bis Schulterhöhe – langsam ablassen.", ""),
            ("Trizepsdrücken über Kopf (Kurzhantel)", 3, "10–12", 60, 2.0, "Ellbogen zeigen nach vorne/oben, nur der Unterarm bewegt sich.", ""),
        ],
    },
    {
        "weekday": 1,
        "kind": "kraft",
        "title": "Unterkörper – Kraft",
        "duration_min": 55,
        "notes": "Am besten vormittags/mittags, mind. 4–6 h vor dem Fußball. Nicht bis zum Muskelversagen (RPE 7–8), damit du beim Training spritzig bist. Geht es nur direkt davor: 2 Sätze pro Übung.",
        "exercises": [
            ("Kniebeuge (Langhantel)", 4, "5", 180, 2.5, "Füße schulterbreit, Knie folgen den Zehen, Rumpf fest. So tief, wie du sauber bleibst (ideal unter parallel).", "Goblet Squat mit Kurzhantel"),
            ("Rumänisches Kreuzheben (Langhantel)", 3, "6–8", 150, 2.5, "Rücken gerade, Knie leicht gebeugt, Hüfte nach hinten schieben bis zur Dehnung in den hinteren Oberschenkeln.", "Mit Kurzhanteln"),
            ("Bulgarische Split Squats (Kurzhanteln)", 3, "8–10", 90, 2.0, "Je Bein. Hinterer Fuß auf Bank/Stuhl, Oberkörper leicht nach vorne, vorderes Knie stabil.", "Ausfallschritte"),
            ("Hip Thrust (Langhantel)", 3, "8–12", 90, 2.5, "Schultern auf Bank oder Sofa, Kinn zur Brust, oben 1 s halten und Gesäß anspannen.", "Glute Bridge am Boden"),
            ("Wadenheben einbeinig (Kurzhantel)", 3, "12–15", 60, 2.0, "Je Bein, auf einer Stufe – unten volle Dehnung, oben kurz halten.", ""),
            ("Hängendes Knieheben", 3, "10–15", 60, 0.0, "An der Klimmzugstange, ohne Schwung, Becken nach oben rollen.", "Liegendes Beinheben"),
        ],
    },
    {
        "weekday": 1,
        "kind": "fussball",
        "title": "Fußballtraining",
        "notes": "Teamtraining. Mit der Garmin als Fußball aufzeichnen – dann fließt die Belastung in Recovery ein.",
        "exercises": [],
    },
    {
        "weekday": 2,
        "kind": "ruhe",
        "title": "Ruhetag",
        "notes": "Erholung: mind. 8 h Schlaf, genug Eiweiß. Optional 10–15 min Mobility oder ein Spaziergang.",
        "exercises": [],
    },
    {
        "weekday": 3,
        "kind": "praevention",
        "title": "Athletik & Verletzungsprävention",
        "duration_min": 20,
        "notes": "15–20 min vor dem Fußballtraining als Teil des Aufwärmens oder direkt danach. Senkt das Risiko für Oberschenkel- und Leistenverletzungen deutlich.",
        "exercises": [
            ("Nordic Hamstring Curls", 3, "4–6", 90, 0.0, "Füße unter Langhantel oder Sofa fixieren, Körper gerade und so langsam wie möglich nach vorne ablassen, mit den Händen abfangen.", "Rutschende Beinbeuger (Sliding Leg Curls)"),
            ("Copenhagen Plank", 3, "20–30 s", 60, 0.0, "Je Seite. Oberes Bein auf der Bank, Hüfte hoch – stärkt die Leiste.", "Einfacher: Knie statt Fuß auf der Bank"),
            ("Einbeiniges Kreuzheben (Kurzhantel)", 2, "8–10", 60, 2.0, "Je Bein. Hüfte bleibt gerade, langsam und kontrolliert – Balance und hintere Kette.", ""),
            ("Squat Jumps", 3, "5", 90, 0.0, "Explosiv nach oben, weich und leise landen. Qualität vor Menge.", ""),
            ("Unterarmstütz (Plank)", 3, "40–60 s", 45, 0.0, "Körper eine Linie, Bauch und Gesäß anspannen.", ""),
        ],
    },
    {
        "weekday": 3,
        "kind": "fussball",
        "title": "Fußballtraining",
        "notes": "Teamtraining. Mit der Garmin als Fußball aufzeichnen.",
        "exercises": [],
    },
    {
        "weekday": 4,
        "kind": "ruhe",
        "title": "Ruhetag",
        "notes": "Erholung vor dem Wochenende. Optional Mobility für Hüfte und hintere Oberschenkel.",
        "exercises": [],
    },
    {
        "weekday": 5,
        "kind": "kraft",
        "title": "Oberkörper B – Ziehen & Rumpf",
        "duration_min": 55,
        "notes": "Tag vor dem Spiel: nur Oberkörper und Rumpf, die Beine bleiben frisch. Nicht bis zum Muskelversagen.",
        "exercises": [
            ("Langhantelrudern vorgebeugt", 4, "6–8", 120, 2.5, "Oberkörper ca. 45° nach vorne, Rücken gerade, Stange zum Bauchnabel ziehen.", "Kurzhantelrudern beidarmig"),
            ("Kurzhantel-Bankdrücken", 3, "8–10", 90, 2.0, "Volle Bewegung, unten kurz Spannung halten.", "Liegestütze mit Rucksack als Zusatzgewicht"),
            ("Klimmzüge (Untergriff)", 3, "6–10", 120, 2.5, "Schulterbreit im Untergriff, kontrolliert ablassen.", "Negative Klimmzüge"),
            ("Arnold Press (Kurzhanteln)", 3, "8–12", 90, 2.0, "Im Sitzen oder Stehen, Hanteln beim Hochdrücken nach außen drehen.", ""),
            ("Reverse Flys vorgebeugt (Kurzhanteln)", 3, "12–15", 60, 1.0, "Leichtes Gewicht, Arme seitlich öffnen – gut für die hintere Schulter und die Haltung.", ""),
            ("Bizepscurls (Langhantel)", 3, "8–12", 60, 2.5, "Ellbogen bleiben am Körper, kein Schwung.", "Kurzhantel-Curls"),
            ("Dead Bug", 3, "10", 45, 0.0, "Je Seite. Lendenwirbelsäule bleibt am Boden, Arm und gegenüberliegendes Bein langsam strecken.", ""),
        ],
    },
    {
        "weekday": 6,
        "kind": "fussball",
        "title": "Fußballspiel",
        "notes": "Spieltag. Danach locker auslaufen, viel trinken, Eiweiß und Kohlenhydrate.",
        "exercises": [],
    },
]


def create_default_plan(db: Session) -> int:
    """Legt den Standardplan an (ersetzt alle vorhandenen Einheiten)."""
    for s in db.query(TrainingSession).all():
        db.delete(s)
    db.flush()
    order: dict[int, int] = {}
    for item in DEFAULT_PLAN:
        idx = order.get(item["weekday"], 0)
        order[item["weekday"]] = idx + 1
        session = TrainingSession(
            weekday=item["weekday"],
            order_index=idx,
            kind=item["kind"],
            title=item["title"],
            notes=item["notes"],
            duration_min=item.get("duration_min"),
        )
        for i, (name, sets, reps, rest, inc, notes, alt) in enumerate(item["exercises"]):
            session.exercises.append(
                PlanExercise(order_index=i, name=name, sets=sets, reps=reps, rest_seconds=rest, increment_kg=inc, notes=notes, alternative=alt)
            )
        db.add(session)
    settings_store.set_value(db, "training_plan_seeded", True, commit=False)
    db.commit()
    return len(DEFAULT_PLAN)


def ensure_plan(db: Session) -> None:
    """Beim ersten Start den Standardplan anlegen (danach nie wieder automatisch)."""
    if settings_store.get(db, "training_plan_seeded", False):
        return
    if db.query(TrainingSession).count() == 0:
        create_default_plan(db)
    else:
        settings_store.set_value(db, "training_plan_seeded", True)


# ---------------------------------------------------------------- Progression


def rep_target(reps: str) -> tuple[int | None, bool]:
    """Obere Wiederholungszahl aus „6–8“, „5“, „30 s“ … und ob es eine Zeitangabe ist."""
    numbers = [int(n) for n in re.findall(r"\d+", reps or "")]
    timed = bool(re.search(r"\d\s*(s|sek|min)\b", (reps or "").lower()))
    return (max(numbers) if numbers else None), timed


def _fmt_kg(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def last_performance(db: Session, name: str, before: date | None = None, exclude_log_id: int | None = None) -> dict[str, Any] | None:
    """Sätze des letzten Trainings, in dem die Übung vorkam."""
    q = (
        db.query(WorkoutLog)
        .join(WorkoutSet, WorkoutSet.log_id == WorkoutLog.id)
        .filter(WorkoutSet.exercise_name == name)
    )
    if before is not None:
        q = q.filter(WorkoutLog.date <= before)
    if exclude_log_id is not None:
        q = q.filter(WorkoutLog.id != exclude_log_id)
    log = q.order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc()).first()
    if log is None:
        return None
    sets = [s for s in log.sets if s.exercise_name == name]
    return {
        "date": log.date.isoformat(),
        "log_id": log.id,
        "sets": [{"set_number": s.set_number, "weight_kg": s.weight_kg, "reps": s.reps, "done": s.done} for s in sets],
    }


def suggestion(ex: PlanExercise, last: dict[str, Any] | None) -> dict[str, Any]:
    """Vorschlag fürs nächste Training nach doppelter Progression."""
    top, timed = rep_target(ex.reps)
    unit = "Sekunden" if timed else "Wiederholungen"
    goal = f"{top} {unit}" if top else unit
    if last is None or not last["sets"]:
        if not ex.increment_kg:
            return {"weight_kg": None, "text": f"Erstes Mal: Trag ein, wie viele {unit} du sauber schaffst."}
        return {"weight_kg": None, "text": "Erstes Mal: Gewicht wählen, mit dem du die Wiederholungen sauber schaffst (1–2 im Tank)."}
    sets = last["sets"]
    weights = [s["weight_kg"] for s in sets if s["weight_kg"] is not None]
    weight = max(weights) if weights else None
    all_done = all(s["done"] for s in sets) and len(sets) >= ex.sets
    hit_top = top is not None and all((s["reps"] or 0) >= top for s in sets)
    if all_done and hit_top:
        if ex.increment_kg and weight is not None:
            new = round(weight + ex.increment_kg, 2)
            return {"weight_kg": new, "increase": True, "text": f"Alle Sätze geschafft – steigere auf {_fmt_kg(new)} kg."}
        return {"weight_kg": weight, "increase": True, "text": f"Alle Sätze geschafft – mach es schwerer: mehr {unit}, Zusatzgewicht oder eine schwierigere Variante."}
    if weight is not None:
        return {"weight_kg": weight, "increase": False, "text": f"Bleib bei {_fmt_kg(weight)} kg und schaff in jedem Satz {goal}."}
    return {"weight_kg": None, "increase": False, "text": f"Ziel: in jedem Satz {goal}."}


def estimated_1rm(weight: float | None, reps: int | None) -> float | None:
    """Geschätztes Maximalgewicht (Epley), nur sinnvoll bis ca. 12 Wiederholungen."""
    if not weight or not reps or reps <= 0:
        return None
    return round(weight * (1 + min(reps, 12) / 30), 1)


def exercise_progress(db: Session, name: str) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkoutSet, WorkoutLog.date)
        .join(WorkoutLog, WorkoutSet.log_id == WorkoutLog.id)
        .filter(WorkoutSet.exercise_name == name)
        .order_by(WorkoutLog.date, WorkoutSet.id)
        .all()
    )
    by_day: dict[date, dict[str, Any]] = {}
    for s, d in rows:
        if not s.done:
            continue
        entry = by_day.setdefault(d, {"date": d.isoformat(), "best_weight": None, "best_reps": 0, "e1rm": None, "volume": 0.0, "sets": 0})
        entry["sets"] += 1
        entry["best_reps"] = max(entry["best_reps"], s.reps or 0)
        if s.weight_kg is not None:
            entry["best_weight"] = max(entry["best_weight"] or 0, s.weight_kg)
            entry["volume"] += s.weight_kg * (s.reps or 0)
        e = estimated_1rm(s.weight_kg, s.reps)
        if e is not None:
            entry["e1rm"] = max(entry["e1rm"] or 0, e)
    out = list(by_day.values())
    for e in out:
        e["volume"] = round(e["volume"])
    return out
