"""Automatische Wochen- und Monatszusammenfassung aller Bereiche."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import (
    Activity,
    DailyMetrics,
    FocusSession,
    Habit,
    HabitLog,
    JournalEntry,
    Meal,
    SleepRecord,
    StudyBlock,
    Todo,
    Transaction,
)
from ..utils import MONTHS_DE, add_months, rnd, safe_mean
from . import recovery
from .agenda import activity_label
from .fitness_stats import category


def period_bounds(period: str, offset: int = 0, today: date | None = None) -> tuple[date, date, str]:
    today = today or date.today()
    if period == "monat":
        start = add_months(today.replace(day=1), -offset)
        end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        label = f"{MONTHS_DE[start.month - 1]} {start.year}"
    else:
        start = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
        end = start + timedelta(days=6)
        label = f"KW {start.isocalendar()[1]} ({start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y')})"
    return start, end, label


def _dt(d: date) -> datetime:
    return datetime.combine(d, time.min)


def summarize(db: Session, start: date, end: date) -> dict[str, Any]:
    today = date.today()
    last = min(end, today)
    days = max(1, (last - start).days + 1) if last >= start else 0
    s = settings_store.get_all(db)

    # Training
    acts = db.query(Activity).filter(Activity.date >= start, Activity.date <= end).all()
    runs = [a for a in acts if category(a.type) == "laufen"]
    longest = max(acts, key=lambda a: a.duration_s or 0, default=None)
    longest_run = max(runs, key=lambda a: a.distance_m or 0, default=None)
    by_cat = Counter(category(a.type) for a in acts)
    training = {
        "sessions": len(acts),
        "hours": rnd(sum(a.duration_s or 0 for a in acts) / 3600, 1),
        "km": rnd(sum(a.distance_m or 0 for a in acts) / 1000, 1),
        "run_km": rnd(sum(a.distance_m or 0 for a in runs) / 1000, 1),
        "load": round(sum(a.training_load or 0 for a in acts)),
        "by_category": dict(by_cat),
        "z2_minutes": round(sum(a.z2_s or 0 for a in acts) / 60),
        "hard_minutes": round(sum((a.z4_s or 0) + (a.z5_s or 0) for a in acts) / 60),
        "longest": {"name": longest.name, "type": activity_label(longest.type), "minutes": round(longest.duration_s / 60)} if longest else None,
        "longest_run_km": rnd(longest_run.distance_m / 1000, 1) if longest_run and longest_run.distance_m else None,
    }

    # Schlaf
    nights = db.query(SleepRecord).filter(SleepRecord.date >= start, SleepRecord.date <= end).all()
    goal = float(s["sleep_goal_hours"])
    best_night = max(nights, key=lambda n: n.score or 0, default=None)
    sleep = {
        "nights": len(nights),
        "avg_hours": rnd(safe_mean(n.duration_s / 3600 for n in nights), 2),
        "avg_score": rnd(safe_mean(n.score for n in nights), 0),
        "avg_deep_h": rnd(safe_mean(n.deep_s / 3600 for n in nights), 2),
        "avg_rem_h": rnd(safe_mean(n.rem_s / 3600 for n in nights), 2),
        "goal_met": sum(1 for n in nights if n.duration_s / 3600 >= goal),
        "goal_h": goal,
        "best_night": {"date": best_night.date.isoformat(), "score": best_night.score} if best_night and best_night.score else None,
    }

    # Recovery
    metrics = db.query(DailyMetrics).filter(DailyMetrics.date >= start, DailyMetrics.date <= end).all()
    colors: Counter[str] = Counter()
    d = start
    while d <= last:
        colors[recovery.evaluate(recovery.build_inputs(db, d))["color"]] += 1
        d += timedelta(days=1)
    rec = {
        "avg_hrv": rnd(safe_mean(m.hrv_last_night for m in metrics), 0),
        "avg_rhr": rnd(safe_mean(m.resting_hr for m in metrics), 1),
        "avg_stress": rnd(safe_mean(m.stress_avg for m in metrics), 0),
        "avg_body_battery": rnd(safe_mean(m.body_battery_wake or m.body_battery_high for m in metrics), 0),
        "avg_steps": rnd(safe_mean(m.steps for m in metrics), 0),
        "traffic_lights": {"gruen": colors.get("gruen", 0), "gelb": colors.get("gelb", 0), "rot": colors.get("rot", 0)},
    }

    # Lernen
    blocks = db.query(StudyBlock).filter(StudyBlock.start >= _dt(start), StudyBlock.start < _dt(end + timedelta(days=1))).all()
    past_blocks = [b for b in blocks if b.end <= datetime.now() or b.status != "geplant"]

    def mins(bs):
        return sum(int((b.end - b.start).total_seconds() // 60) for b in bs)

    done_blocks = [b for b in blocks if b.status == "erledigt"]
    per_subject: dict[str, int] = defaultdict(int)
    for b in done_blocks:
        per_subject[b.subject.name if b.subject else "?"] += mins([b])
    focus = db.query(FocusSession).filter(FocusSession.start >= _dt(start), FocusSession.start < _dt(end + timedelta(days=1))).all()
    study = {
        "planned_minutes": mins(blocks),
        "done_minutes": mins(done_blocks),
        "missed_blocks": sum(1 for b in blocks if b.status == "verpasst"),
        "done_blocks": len(done_blocks),
        "completion": round(len(done_blocks) / len(past_blocks) * 100) if past_blocks else None,
        "focus_minutes": round(sum(f.minutes for f in focus)),
        "focus_sessions": len(focus),
        "per_subject": dict(sorted(per_subject.items(), key=lambda x: -x[1])),
    }

    # Habits
    active = db.query(Habit).filter(Habit.active.is_(True)).all()
    logs = db.query(HabitLog).filter(HabitLog.date >= start, HabitLog.date <= last).all()
    counts = Counter(l.habit_id for l in logs if any(h.id == l.habit_id for h in active))
    best = max(active, key=lambda h: counts.get(h.id, 0), default=None)
    habits = {
        "rate": round(sum(counts.values()) / (len(active) * days) * 100) if active and days else None,
        "best": {"name": best.name, "emoji": best.emoji, "days": counts.get(best.id, 0)} if best and counts else None,
        "checks": sum(counts.values()),
    }

    # To-dos
    todos = {
        "completed": db.query(Todo).filter(Todo.done_at >= _dt(start), Todo.done_at < _dt(end + timedelta(days=1))).count(),
        "created": db.query(Todo).filter(Todo.created_at >= _dt(start), Todo.created_at < _dt(end + timedelta(days=1))).count(),
        "open_overdue": db.query(Todo).filter(Todo.done.is_(False), Todo.due_date < today).count(),
    }

    # Ernährung
    meals = db.query(Meal).filter(Meal.date >= start, Meal.date <= end).all()
    per_day_kcal: dict[date, float] = defaultdict(float)
    per_day_protein: dict[date, float] = defaultdict(float)
    for m in meals:
        per_day_kcal[m.date] += m.kcal
        per_day_protein[m.date] += m.protein
    burned = {m.date: m.calories_total for m in metrics if m.calories_total}
    balances = [per_day_kcal[d] - burned[d] for d in per_day_kcal if d in burned and d < today]
    nutrition = {
        "days_logged": len(per_day_kcal),
        "avg_kcal": rnd(safe_mean(per_day_kcal.values()), 0),
        "avg_protein": rnd(safe_mean(per_day_protein.values()), 0),
        "avg_balance": rnd(safe_mean(balances), 0),
        "kcal_goal": s["kcal_goal"],
    }

    # Finanzen
    txs = db.query(Transaction).filter(Transaction.date >= start, Transaction.date <= end).all()
    spend: dict[str, float] = defaultdict(float)
    for t in txs:
        if t.kind == "ausgabe":
            spend[t.category] += t.amount
    income = sum(t.amount for t in txs if t.kind == "einnahme")
    expense = sum(t.amount for t in txs if t.kind == "ausgabe")
    top = max(spend.items(), key=lambda x: x[1], default=None)
    finance = {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "saldo": round(income - expense, 2),
        "top_category": {"category": top[0], "amount": round(top[1], 2)} if top else None,
    }

    # Journal
    entries = db.query(JournalEntry).filter(JournalEntry.date >= start, JournalEntry.date <= end).all()
    journal = {
        "entries": len(entries),
        "avg_mood": rnd(safe_mean(e.mood for e in entries), 1),
        "best_day": max((e for e in entries if e.mood), key=lambda e: e.mood, default=None).date.isoformat() if any(e.mood for e in entries) else None,
    }

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "training": training,
        "sleep": sleep,
        "recovery": rec,
        "study": study,
        "habits": habits,
        "todos": todos,
        "nutrition": nutrition,
        "finance": finance,
        "journal": journal,
    }


def _fmt(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def highlights(cur: dict[str, Any], prev: dict[str, Any]) -> list[dict[str, str]]:
    """Kurze Stichpunkte (positiv/negativ) für die Zusammenfassung."""
    out: list[dict[str, str]] = []
    t, pt = cur["training"], prev["training"]
    if t["sessions"]:
        diff = (t["hours"] or 0) - (pt["hours"] or 0)
        out.append({"tone": "good" if diff >= 0 else "neutral", "icon": "🏃", "text": f"{t['sessions']} Einheiten, {_fmt(t['hours'])} h Training ({'+' if diff >= 0 else '−'}{_fmt(abs(diff))} h zum Vorzeitraum)."})
    if t["longest_run_km"]:
        out.append({"tone": "good", "icon": "🏅", "text": f"Längster Lauf: {_fmt(t['longest_run_km'])} km."})
    sl = cur["sleep"]
    if sl["nights"]:
        tone = "good" if sl["goal_met"] >= sl["nights"] * 0.6 else "bad"
        out.append({"tone": tone, "icon": "🌙", "text": f"Schlafziel in {sl['goal_met']} von {sl['nights']} Nächten erreicht, Ø {_fmt(sl['avg_hours'], 1)} h, Score {int(sl['avg_score'] or 0)}."})
    tl = cur["recovery"]["traffic_lights"]
    if sum(tl.values()):
        out.append({"tone": "bad" if tl["rot"] >= 2 else "neutral", "icon": "🚦", "text": f"Ampel: {tl['gruen']}× grün, {tl['gelb']}× gelb, {tl['rot']}× rot."})
    st = cur["study"]
    if st["done_minutes"] or st["missed_blocks"]:
        tone = "good" if (st["completion"] or 0) >= 75 else "bad"
        out.append({"tone": tone, "icon": "📚", "text": f"{_fmt(st['done_minutes'] / 60)} h gelernt ({st['done_blocks']} Blöcke), {st['missed_blocks']} verpasst."})
    if st["focus_minutes"]:
        out.append({"tone": "good", "icon": "🍅", "text": f"{st['focus_sessions']} Fokus-Sessions mit {_fmt(st['focus_minutes'] / 60)} h Fokuszeit."})
    hb = cur["habits"]
    if hb["rate"] is not None:
        extra = f", stärkster Habit: {hb['best']['emoji']} {hb['best']['name']}" if hb["best"] else ""
        out.append({"tone": "good" if hb["rate"] >= 70 else "neutral", "icon": "✅", "text": f"Habits zu {hb['rate']} % erfüllt{extra}."})
    if cur["todos"]["completed"]:
        n = cur["todos"]["completed"]
        out.append({"tone": "good", "icon": "📝", "text": f"{n} {'Aufgabe' if n == 1 else 'Aufgaben'} erledigt."})
    if cur["todos"]["open_overdue"]:
        n = cur["todos"]["open_overdue"]
        out.append({"tone": "bad", "icon": "⏰", "text": f"{n} überfällige {'Aufgabe' if n == 1 else 'Aufgaben'} offen."})
    fi = cur["finance"]
    if fi["income"] or fi["expense"]:
        out.append({"tone": "good" if fi["saldo"] >= 0 else "bad", "icon": "💶", "text": f"Saldo {_fmt(fi['saldo'], 2)} € (Ausgaben {_fmt(fi['expense'], 2)} €)."})
    if cur["journal"]["avg_mood"]:
        out.append({"tone": "neutral", "icon": "📓", "text": f"Ø Stimmung {_fmt(cur['journal']['avg_mood'])} von 5 bei {cur['journal']['entries']} Journal-Einträgen."})
    return out


def build_review(db: Session, period: str = "woche", offset: int = 0) -> dict[str, Any]:
    start, end, label = period_bounds(period, offset)
    if period == "monat":
        p_start = add_months(start, -1)
        p_end = start - timedelta(days=1)
    else:
        p_start, p_end = start - timedelta(weeks=1), start - timedelta(days=1)
    today = date.today()
    running = start <= today <= end
    if running:
        # Laufender Zeitraum: fair mit den gleichen Tagen des Vorzeitraums vergleichen
        p_end = min(p_end, p_start + (today - start))
    cur = summarize(db, start, end)
    prev = summarize(db, p_start, p_end)
    return {
        "period": period,
        "offset": offset,
        "label": label,
        "current": cur,
        "previous": prev,
        "highlights": highlights(cur, prev),
        "is_running": running,
        "compare_days": (p_end - p_start).days + 1,
    }
