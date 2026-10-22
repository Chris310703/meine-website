"""Trainingsplan: Standardplan für Chris, letzte Leistungen und Progressionsvorschläge."""

from __future__ import annotations

import hashlib
import json
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
    "goal": "Athletisch und funktionell: Kraft, Schnelligkeit und ein starker Rumpf – ohne Bodybuilding. Zwei Ganzkörper-Einheiten (Mo, Fr) ergänzen den Fußball (Di, Do, So), Ruhetage sind Mittwoch und Samstag.",
    "rules": [
        "Athletik statt Bodybuilding: Die Hauptübungen mit wenigen Wiederholungen (4–6) und schwerem Gewicht machen dich stärker und schneller, ohne viel Masse aufzubauen. Die Ergänzungsübungen (8–12 Wdh.) sorgen für eine athletische, definierte Figur.",
        "Tempo: jede Wiederholung explosiv nach oben, kontrolliert nach unten. Nie bis zum Muskelversagen – immer 2 Wiederholungen im Tank lassen (RPE 7–8).",
        "Doppelte Progression: Schaffst du in allen Sätzen die obere Wiederholungszahl sauber, nimmst du beim nächsten Mal mehr Gewicht (Langhantel +2,5 kg, Kurzhanteln +1–2 kg). Sonst gleiches Gewicht und eine Wiederholung mehr anpeilen. Bei Sprüngen zählt nicht mehr Gewicht, sondern Weite und Explosivität.",
        "Core an jedem Krafttag: Anti-Rotation, Seitstütz, Rollouts und Carries machen dich im Zweikampf stabiler und schützen Rücken und Leiste. Dazu optional der 10-Minuten-Core-Finisher nach dem Fußball am Dienstag.",
        "Montag ist der Tag nach dem Spiel: Sind die Beine noch platt, Kniebeuge und Kreuzheben auf 2–3 Sätze kürzen – Oberkörper und Core normal machen.",
        "Freitag ist zwei Tage vor dem Spiel: wenig Volumen, viel Tempo. Fühlen sich die Beine schwer an, Sprünge und Split Squats auf 2 Sätze kürzen.",
        "Handball am Montag: Dann zählt Handball als Athletik-Einheit und Ganzkörper A fällt aus. Mach am Freitag zusätzlich Kniebeuge und Bankdrücken (je 3 Sätze) aus Einheit A.",
        "Aufwärmen (5–8 min): Seilspringen oder lockeres Hüpfen, Hüft- und Schulter-Mobility, dann 2 leichte Aufwärmsätze bei der ersten Übung.",
        "Alle 6 Wochen eine leichtere Woche (Deload): Gewichte etwa −20 %, nur die Hälfte der Sätze. Recovery-Ampel rot oder sehr schlechter Schlaf: Einheit locker machen oder ausfallen lassen.",
        "Ernährung: ca. 1,6–2 g Eiweiß pro kg Körpergewicht, an Fußballtagen und vor dem Spiel genug Kohlenhydrate.",
    ],
}

PLAN_VERSION = 2

# Wochenplan: Fußball Di/Do (Training) und So (Spiel), Ruhetage Mi/Sa, manchmal Handball am Montag.
# An Fußballtagen kein Krafttraining vorher (vormittags geht nicht).
DEFAULT_PLAN: list[dict[str, Any]] = [
    {
        "weekday": 0,
        "kind": "kraft",
        "title": "Ganzkörper A – Kraft & Core",
        "duration_min": 65,
        "notes": "Tag nach dem Spiel – der Hauptkrafttag der Woche. Schwer, aber sauber und explosiv, immer 2 Wiederholungen im Tank. Sind die Beine vom Spiel noch platt, Kniebeuge und Kreuzheben auf 2–3 Sätze kürzen. Montags Handball? Dann fällt diese Einheit aus (siehe „So funktioniert der Plan“).",
        "exercises": [
            ("Kniebeuge (Langhantel)", 4, "4–6", 180, 2.5, "Kontrolliert runter, explosiv hoch. Füße schulterbreit, Knie folgen den Zehen, Rumpf fest. So tief, wie du sauber bleibst.", "Frontkniebeuge oder Goblet Squat"),
            ("Klimmzüge (Obergriff)", 4, "5–8", 150, 2.5, "Unten ganz strecken, explosiv die Brust zur Stange ziehen. Schaffst du 4 × 8, mit Zusatzgewicht (Kurzhantel zwischen den Füßen) – eingetragen wird das Zusatzgewicht.", "Negative Klimmzüge: hochspringen, 5 s ablassen"),
            ("Bankdrücken (Langhantel)", 4, "4–6", 150, 2.5, "Schulterblätter zusammen und nach unten, Füße fest am Boden. Stange kontrolliert zur Brust, explosiv hochdrücken.", "Ohne Bank: Bodendrücken (Floor Press)"),
            ("Rumänisches Kreuzheben (Langhantel)", 3, "6–8", 150, 2.5, "Rücken gerade, Knie leicht gebeugt, Hüfte nach hinten schieben bis zur Dehnung in den hinteren Oberschenkeln, dann die Hüfte kräftig nach vorne bringen.", "Mit Kurzhanteln"),
            ("Einarmiges Kurzhantelrudern", 3, "8–10", 90, 2.0, "Je Seite. Rücken gerade und nicht verdrehen – so arbeitet der Rumpf gleich mit.", ""),
            ("Nordic Hamstring Curls", 3, "4–6", 90, 0.0, "Füße unter Langhantel oder Sofa fixieren, Körper gerade und so langsam wie möglich nach vorne ablassen, mit den Händen abfangen. Der beste Schutz vor Zerrungen im hinteren Oberschenkel.", "Rutschende Beinbeuger (Sliding Leg Curls)"),
            ("Langhantel-Rollout", 3, "6–10", 60, 0.0, "Core: Aus dem Kniestand die Stange nach vorne rollen, Bauch und Gesäß fest, kein Hohlkreuz – nur so weit, wie der Rücken gerade bleibt.", "Ab Wheel oder Unterarmstütz 3 × 45 s"),
            ("Suitcase Carry (Kurzhantel)", 3, "30–40 s", 60, 2.0, "Core: Schwere Kurzhantel in einer Hand, aufrecht gehen, ohne zur Seite zu kippen. Je Seite.", "Seitstütz 3 × 30 s je Seite"),
        ],
    },
    {
        "weekday": 1,
        "kind": "fussball",
        "title": "Fußballtraining",
        "notes": "Teamtraining – vorher kein Krafttraining. Mit der Garmin als Fußball aufzeichnen, dann fließt die Belastung in Recovery ein.",
        "exercises": [],
    },
    {
        "weekday": 1,
        "kind": "praevention",
        "title": "Core-Finisher (optional, 10 min)",
        "duration_min": 10,
        "notes": "Direkt nach dem Fußball oder abends zu Hause – nur wenn du dich gut fühlst. Kurz, aber wirkungsvoll für Rumpf und Leiste.",
        "exercises": [
            ("Copenhagen Plank", 2, "20–30 s", 45, 0.0, "Je Seite. Oberes Bein auf Bank oder Stuhl, Hüfte hoch – stärkt die Leiste (Adduktoren).", "Einfacher: Knie statt Fuß auflegen"),
            ("Dead Bug", 2, "8–10", 30, 0.0, "Je Seite. Lendenwirbelsäule bleibt am Boden, Arm und gegenüberliegendes Bein langsam strecken und dabei ausatmen.", ""),
            ("Seitstütz", 2, "30–45 s", 30, 0.0, "Je Seite. Körper eine Linie, Hüfte nicht absinken lassen.", "Schwerer: oberen Arm unter dem Körper durchfädeln"),
            ("Hollow Body Hold", 2, "20–30 s", 30, 0.0, "Rücken flach am Boden, Arme und Beine gestreckt knapp über dem Boden halten.", "Einfacher: Knie angewinkelt"),
        ],
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
        "kind": "fussball",
        "title": "Fußballtraining",
        "notes": "Teamtraining – vorher kein Krafttraining. Mit der Garmin als Fußball aufzeichnen.",
        "exercises": [],
    },
    {
        "weekday": 4,
        "kind": "kraft",
        "title": "Ganzkörper B – Athletik, Power & Core",
        "duration_min": 55,
        "notes": "Zwei Tage vor dem Spiel: wenig Volumen, viel Tempo. Sprünge und Snatches mit voller Erholung, alles explosiv – kein Satz bis zum Versagen. Fühlen sich die Beine schwer an, Sprünge und Split Squats auf 2 Sätze kürzen.",
        "exercises": [
            ("Standweitsprung (Broad Jump)", 4, "3", 90, 0.0, "Aus dem Stand maximal weit springen, Arme mitschwingen, weich und stabil landen. Jeder Sprung mit voller Spannung – Qualität vor Menge.", "Box Jumps auf eine stabile Erhöhung"),
            ("Kurzhantel-Snatch einarmig", 3, "4", 90, 2.0, "Je Seite. Hantel zwischen den Füßen, Hüfte explosiv strecken und die Hantel in einer Bewegung über Kopf bringen – Schnellkraft wie beim Antritt oder Kopfball.", "Kurzhantel-Swing"),
            ("Bulgarische Split Squats (Kurzhanteln)", 3, "6–8", 90, 2.0, "Je Bein. Hinterer Fuß auf Bank oder Stuhl, aus der Tiefe kräftig hochdrücken. Einbeinig = direkt übertragbar auf Sprint und Schuss.", "Ausfallschritte"),
            ("Schulterdrücken stehend (Langhantel)", 3, "5–8", 120, 2.5, "Gesäß und Bauch fest, kein Hohlkreuz – im Stehen arbeitet der ganze Rumpf mit.", "Kurzhantel-Schulterdrücken"),
            ("Klimmzüge (Untergriff)", 3, "6–10", 120, 2.5, "Schulterbreit im Untergriff, explosiv hoch, kontrolliert ablassen.", "Negative Klimmzüge"),
            ("Einbeiniges Kreuzheben (Kurzhantel)", 2, "8", 60, 2.0, "Je Bein. Hüfte bleibt gerade, langsam und kontrolliert – Balance und stabile Sprunggelenke.", ""),
            ("Hängendes Beinheben", 3, "8–12", 60, 0.0, "Core: An der Klimmzugstange ohne Schwung, Becken nach oben rollen und langsam ablassen.", "Hängendes Knieheben"),
            ("Copenhagen Plank", 2, "20–30 s", 45, 0.0, "Je Seite. Oberes Bein auf der Bank, Hüfte hoch – stärkt die Leiste.", "Einfacher: Knie statt Fuß auflegen"),
        ],
    },
    {
        "weekday": 5,
        "kind": "ruhe",
        "title": "Ruhetag",
        "notes": "Tag vor dem Spiel: Beine schonen, früh schlafen, Kohlenhydrate und genug trinken. Optional 10 min lockere Mobility.",
        "exercises": [],
    },
    {
        "weekday": 6,
        "kind": "fussball",
        "title": "Fußballspiel",
        "notes": "Spieltag. Danach locker auslaufen, viel trinken, Eiweiß und Kohlenhydrate.",
        "exercises": [],
    },
]

# Fingerabdrücke früherer, unveränderter Standardpläne – sie werden beim Start automatisch ersetzt.
LEGACY_PLAN_SIGNATURES = {
    "d1c00bdf8c37309e0b41ae1dfb4b08cc8ebaf610b1e47035aeaf058b039c5d54",  # Version 1: Ruhetage Mi/Fr, Kraft vor dem Fußball
}


def _signature(rows: list[list[Any]]) -> str:
    rows = sorted(rows, key=lambda r: (r[0], r[1]))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def default_plan_signature(plan: list[dict[str, Any]]) -> str:
    order: dict[int, int] = {}
    rows = []
    for item in plan:
        idx = order.get(item["weekday"], 0)
        order[item["weekday"]] = idx + 1
        exercises = [[n, s, r, rest, float(inc), no, alt] for (n, s, r, rest, inc, no, alt) in item["exercises"]]
        rows.append([item["weekday"], idx, item["kind"], item["title"], item["notes"], item.get("duration_min"), exercises])
    return _signature(rows)


def db_plan_signature(db: Session) -> str:
    rows = []
    for s in db.query(TrainingSession).all():
        exercises = [
            [e.name, e.sets, e.reps, e.rest_seconds, float(e.increment_kg), e.notes, e.alternative]
            for e in sorted(s.exercises, key=lambda x: (x.order_index, x.id))
        ]
        rows.append([s.weekday, s.order_index, s.kind, s.title, s.notes, s.duration_min, exercises])
    return _signature(rows)


def create_default_plan(db: Session) -> int:
    """Legt den Standardplan an (ersetzt alle vorhandenen Einheiten, das Trainingstagebuch bleibt)."""
    # Einträge im Tagebuch von den alten Einheiten lösen (Übungsnamen bleiben, damit Verlauf und Vorschläge erhalten bleiben)
    db.query(WorkoutSet).filter(WorkoutSet.exercise_id.isnot(None)).update({WorkoutSet.exercise_id: None}, synchronize_session=False)
    db.query(WorkoutLog).filter(WorkoutLog.session_id.isnot(None)).update({WorkoutLog.session_id: None}, synchronize_session=False)
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
    settings_store.set_value(db, "training_plan_version", PLAN_VERSION, commit=False)
    db.commit()
    db.expire_all()
    return len(DEFAULT_PLAN)


def ensure_plan(db: Session) -> None:
    """Beim ersten Start den Standardplan anlegen. Ein unveränderter älterer Standardplan wird
    durch den aktuellen ersetzt – selbst angepasste Pläne bleiben unangetastet."""
    if not settings_store.get(db, "training_plan_seeded", False):
        if db.query(TrainingSession).count() == 0:
            create_default_plan(db)
        else:
            settings_store.set_value(db, "training_plan_seeded", True, commit=False)
            settings_store.set_value(db, "training_plan_version", PLAN_VERSION)
        return
    if int(settings_store.get(db, "training_plan_version", 1) or 1) >= PLAN_VERSION:
        return
    if db_plan_signature(db) in LEGACY_PLAN_SIGNATURES:
        create_default_plan(db)
    else:
        settings_store.set_value(db, "training_plan_version", PLAN_VERSION)


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
