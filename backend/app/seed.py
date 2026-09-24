"""Beispieldaten, damit die App ohne Logins sofort etwas zeigt.

Alle Datensätze sind mit is_demo=True markiert und lassen sich unter
Einstellungen → Daten wieder löschen. Die Daten werden relativ zum heutigen
Datum erzeugt, sind also immer „aktuell“.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import settings_store
from .models import (
    Activity,
    CalendarEvent,
    DailyMetrics,
    FocusSession,
    Habit,
    HabitLog,
    JournalEntry,
    Meal,
    NewsFeed,
    NewsItem,
    PlannedWorkout,
    PriceCache,
    SleepRecord,
    StockPosition,
    StudyBlock,
    StudyDocument,
    Subject,
    TimetableEntry,
    Todo,
    Topic,
    Transaction,
)

DEMO_MODELS = [
    FocusSession,
    StudyBlock,
    StudyDocument,
    Topic,
    TimetableEntry,
    Todo,
    Subject,
    Activity,
    DailyMetrics,
    SleepRecord,
    PlannedWorkout,
    Meal,
    HabitLog,
    Habit,
    JournalEntry,
    Transaction,
    StockPosition,
    NewsItem,
    NewsFeed,
    CalendarEvent,
]

DEFAULT_FEEDS = [
    ("Tagesschau Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml", "Wirtschaft"),
    ("Spiegel Wirtschaft", "https://www.spiegel.de/wirtschaft/index.rss", "Wirtschaft"),
    ("FAZ Wirtschaft", "https://www.faz.net/rss/aktuell/wirtschaft/", "Wirtschaft"),
    ("LTO – Legal Tribune Online", "https://www.lto.de/rss/feed/", "Recht"),
    ("Tagesschau Inland", "https://www.tagesschau.de/inland/index~rss2.xml", "Recht"),
    (
        "Bundesfinanzministerium",
        "https://www.bundesfinanzministerium.de/SiteGlobals/Functions/RSSFeed/DE/Aktuelles/RSSAktuelles.xml",
        "Steuern",
    ),
    ("Sportschau", "https://www.sportschau.de/index~rss2.xml", "Sport"),
    ("kicker", "https://newsfeed.kicker.de/news/aktuell", "Sport"),
]


def is_seeded(db: Session) -> bool:
    return bool(settings_store.get(db, "demo_seeded", False))


def remove_demo_data(db: Session) -> None:
    for model in DEMO_MODELS:
        db.execute(delete(model).where(model.is_demo.is_(True)))
    db.execute(delete(PriceCache).where(PriceCache.source == "demo"))
    settings_store.set_value(db, "demo_active", False, commit=False)
    db.commit()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def seed_demo_data(db: Session, today: date | None = None) -> None:
    today = today or date.today()
    rng = random.Random(42)

    settings_store.set_value(db, "demo_active", True, commit=False)
    _seed_settings(db, today)
    _seed_fitness(db, today, rng)
    subjects = _seed_study(db, today, rng)
    _seed_calendar(db, today)
    _seed_daily_life(db, today, rng, subjects)
    _seed_finance(db, today, rng)
    _seed_stocks(db, today, rng)
    _seed_news(db, today)

    settings_store.set_value(db, "demo_seeded", True, commit=False)
    settings_store.set_value(db, "demo_active", True, commit=False)
    db.commit()

    # Lernplan aus den Beispielfächern erzeugen – mit einer realistischen Vorgeschichte
    try:
        _seed_study_history(db, today, rng)
    except Exception:  # pragma: no cover – Beispieldaten dürfen den Start nie verhindern
        import logging

        logging.getLogger("lifeos.seed").exception("Beispiel-Lernplan konnte nicht erzeugt werden")


def _seed_study_history(db: Session, today: date, rng: random.Random) -> None:
    """Plant so, als hätte Chris vor 8 Tagen begonnen, und markiert die vergangenen Blöcke
    überwiegend als erledigt (einige verpasst). Danach wird ab jetzt neu geplant."""
    from .services import study_service

    now = datetime.now() if today == date.today() else datetime.combine(today, time(7, 0))
    study_service.replan(db, now=datetime.combine(today - timedelta(days=8), time(7, 0)))
    past = (
        db.query(StudyBlock)
        .filter(StudyBlock.status == "geplant", StudyBlock.end < now)
        .order_by(StudyBlock.start)
        .all()
    )
    for block in past:
        block.status = "verpasst" if rng.random() < 0.2 else "erledigt"
    db.commit()
    for topic in db.query(Topic).all():
        study_service.update_topic_status(db, topic)
    db.commit()
    study_service.replan(db, now=now)


# ---------------------------------------------------------------- Einstellungen


def _seed_settings(db: Session, today: date) -> None:
    sem = settings_store.get(db, "semester") or {}
    if not sem.get("start"):
        start = _monday(today) - timedelta(weeks=3)
        settings_store.set_value(
            db,
            "semester",
            {"name": "Wintersemester (Beispiel)", "start": start.isoformat(), "end": (start + timedelta(weeks=17)).isoformat()},
            commit=False,
        )


# ---------------------------------------------------------------- Fitness


def _seed_fitness(db: Session, today: date, rng: random.Random) -> None:
    days = 120
    start = today - timedelta(days=days - 1)
    acute: list[float] = []
    loads: dict[date, float] = {}

    # Wochenplan: 0=Mo … 6=So
    plan = {
        0: ("strength_training", "Krafttraining Oberkörper", 50),
        1: ("running", "Intervalle 6×800 m", 55),
        2: ("running", "Lockerer Lauf Zone 2", 50),
        3: ("strength_training", "Krafttraining Beine & Core", 55),
        5: ("running", "Langer Lauf", 95),
        6: ("cycling", "Radtour", 80),
    }
    act_id = 900000
    for i in range(days):
        day = start + timedelta(days=i)
        progress = i / days  # 0 → 1, Fitness verbessert sich
        if day == today:
            break  # heutige Einheit noch nicht absolviert
        entry = plan.get(day.weekday())
        if entry is None or rng.random() < 0.08:
            loads[day] = 0
            continue
        type_key, name, base_min = entry
        minutes = base_min * rng.uniform(0.9, 1.12)
        hour = 18 if day.weekday() < 5 else 9
        start_time = datetime.combine(day, time(hour, rng.choice([0, 15, 30])))
        duration_s = minutes * 60
        act_id += 1
        a = Activity(
            garmin_id=f"demo-{act_id}",
            start_time=start_time,
            date=day,
            type=type_key,
            name=name,
            duration_s=round(duration_s),
            is_demo=True,
        )
        if type_key == "running":
            if "Intervalle" in name:
                pace = 5.05 - 0.25 * progress + rng.uniform(-0.08, 0.08)  # min/km
                hr = rng.uniform(158, 166)
                zones = [0.08, 0.27, 0.2, 0.3, 0.15]
                load = rng.uniform(140, 190)
                a.aerobic_te, a.anaerobic_te = round(rng.uniform(3.3, 4.0), 1), round(rng.uniform(2.2, 3.1), 1)
            else:
                # Zone-2-Pace bei ~140 bpm wird im Zeitraum schneller (6:20 → 5:55)
                hr = rng.uniform(136, 146)
                pace_at_140 = 6.33 - 0.42 * progress + rng.uniform(-0.07, 0.07)
                pace = pace_at_140 * (140 / hr)
                zones = [0.12, 0.72, 0.14, 0.02, 0.0]
                load = rng.uniform(60, 95) * minutes / 50
                a.aerobic_te, a.anaerobic_te = round(rng.uniform(2.6, 3.4), 1), round(rng.uniform(0, 0.6), 1)
            speed = 1000 / (pace * 60)
            a.avg_speed = round(speed, 3)
            a.distance_m = round(speed * duration_s)
            a.avg_hr = round(hr)
            a.max_hr = round(hr + rng.uniform(12, 22))
            a.elevation_gain = round(rng.uniform(20, 140))
            a.calories = round(minutes * rng.uniform(11, 13.5))
            a.vo2max = round(50.2 + 2.1 * progress + rng.uniform(-0.2, 0.2), 1)
        elif type_key == "cycling":
            speed = rng.uniform(6.8, 7.8)
            a.avg_speed = round(speed, 2)
            a.distance_m = round(speed * duration_s)
            a.avg_hr = round(rng.uniform(128, 138))
            a.max_hr = round(a.avg_hr + rng.uniform(15, 25))
            a.calories = round(minutes * rng.uniform(9, 10.5))
            a.elevation_gain = round(rng.uniform(150, 450))
            zones = [0.25, 0.55, 0.17, 0.03, 0.0]
            load = rng.uniform(70, 110)
            a.aerobic_te, a.anaerobic_te = round(rng.uniform(2.4, 3.2), 1), 0.2
        else:
            a.avg_hr = round(rng.uniform(112, 125))
            a.max_hr = round(a.avg_hr + rng.uniform(25, 40))
            a.calories = round(minutes * rng.uniform(6.5, 8))
            zones = [0.55, 0.3, 0.12, 0.03, 0.0]
            load = rng.uniform(35, 60)
            a.aerobic_te, a.anaerobic_te = round(rng.uniform(1.5, 2.3), 1), round(rng.uniform(0.8, 1.6), 1)
        a.training_load = round(load)
        for z in range(5):
            setattr(a, f"z{z + 1}_s", round(duration_s * zones[z]))
        loads[day] = load
        db.add(a)

    # Tageswerte, Schlaf
    hrv_hist: list[float] = []
    for i in range(days):
        day = start + timedelta(days=i)
        progress = i / days
        yesterday_load = loads.get(day - timedelta(days=1), 0)
        acute.append(loads.get(day, 0))
        acute_7 = sum(acute[-7:]) / 7
        chronic_28 = sum(acute[-28:]) / min(len(acute), 28)
        bad_day = rng.random() < 0.1 and day != today

        # Schlaf
        bedtime_min = 23 * 60 + 10 + rng.gauss(0, 28) + (35 if day.weekday() in (5, 6) else 0)
        if bad_day:
            bedtime_min += 70
        duration_h = max(5.0, min(9.2, rng.gauss(7.45, 0.55) - (1.2 if bad_day else 0)))
        if day == today:
            bedtime_min, duration_h = 23 * 60 + 5, 7.8
        sleep_start = datetime.combine(day - timedelta(days=1), time(0, 0)) + timedelta(minutes=bedtime_min)
        awake_s = duration_h * 3600 * rng.uniform(0.03, 0.06)
        total_s = duration_h * 3600
        deep = total_s * rng.uniform(0.15, 0.21)
        rem = total_s * rng.uniform(0.19, 0.25)
        light = total_s - deep - rem
        sleep_end = sleep_start + timedelta(seconds=total_s + awake_s)
        score = max(38, min(96, 55 + (duration_h - 6) * 14 + rng.gauss(0, 5) - (10 if bad_day else 0)))
        if day == today:
            score = 84

        # HRV & Ruhepuls
        hrv = 54 + 5 * progress + rng.gauss(0, 4) - (12 if bad_day else 0) - (4 if yesterday_load > 150 else 0)
        if day == today:
            hrv = 61
        hrv_hist.append(hrv)
        weekly = sum(hrv_hist[-7:]) / len(hrv_hist[-7:])
        rhr = 51 - 2 * progress + rng.gauss(0, 1.1) + (5 if bad_day else 0) + (1.5 if yesterday_load > 150 else 0)
        if day == today:
            rhr = 49
        status = "BALANCED" if 48 <= weekly <= 66 else ("LOW" if weekly < 48 else "UNBALANCED")
        if bad_day and rng.random() < 0.5:
            status = "UNBALANCED"

        bb_wake = max(15, min(100, 40 + score * 0.6 + rng.gauss(0, 6) - (15 if bad_day else 0)))
        if day == today:
            bb_wake = 86
        active_kcal = (loads.get(day, 0) * 4.2) + rng.uniform(250, 480)
        ratio = acute_7 / chronic_28 if chronic_28 else 1.0
        recovery_h = max(0.0, (yesterday_load / 3.2) - 18 + rng.uniform(-4, 4)) if yesterday_load else 0.0
        readiness = max(12, min(97, 0.45 * score + 0.35 * bb_wake + 12 - recovery_h * 0.6 + rng.gauss(0, 4)))
        if day == today:
            readiness, recovery_h, ratio = 78, 3.0, 1.08
        level = "HIGH" if readiness >= 75 else "MODERATE" if readiness >= 50 else "LOW" if readiness >= 25 else "POOR"
        is_today = day == today
        steps = int(rng.uniform(6500, 13500) + (3000 if loads.get(day, 0) > 0 else 0))
        if is_today:
            steps = 4200

        db.add(
            DailyMetrics(
                date=day,
                steps=steps,
                step_goal=10000,
                calories_total=round(1830 + (active_kcal if not is_today else 420)),
                calories_active=round(active_kcal if not is_today else 420),
                calories_bmr=1830,
                resting_hr=round(rhr),
                stress_avg=round(max(12, min(60, rng.gauss(29, 7) + (12 if bad_day else 0)))),
                stress_max=round(rng.uniform(70, 95)),
                body_battery_high=round(bb_wake),
                body_battery_low=round(max(5, bb_wake - rng.uniform(45, 70))),
                body_battery_wake=round(bb_wake),
                body_battery_charged=round(rng.uniform(40, 75)),
                body_battery_drained=round(rng.uniform(45, 80)),
                hrv_last_night=round(hrv),
                hrv_weekly_avg=round(weekly),
                hrv_baseline_low=48,
                hrv_baseline_high=66,
                hrv_status=status,
                training_readiness=round(readiness),
                training_readiness_level=level,
                recovery_time_h=round(recovery_h, 1),
                acute_load=round(acute_7 * 7),
                chronic_load=round(chronic_28 * 7),
                acwr=round(ratio, 2),
                training_status="Produktiv" if 0.9 <= ratio <= 1.3 else ("Erhaltend" if ratio < 0.9 else "Überlastung"),
                vo2max=round(50.2 + 2.1 * progress, 1),
                intensity_minutes=round(loads.get(day, 0) * 0.5),
                is_demo=True,
            )
        )
        db.add(
            SleepRecord(
                date=day,
                sleep_start=sleep_start.replace(second=0, microsecond=0),
                sleep_end=sleep_end.replace(second=0, microsecond=0),
                duration_s=round(total_s),
                deep_s=round(deep),
                light_s=round(light),
                rem_s=round(rem),
                awake_s=round(awake_s),
                score=round(score),
                score_qualifier="GOOD" if score >= 80 else "FAIR" if score >= 60 else "POOR",
                avg_hrv=round(hrv),
                resting_hr=round(rhr),
                is_demo=True,
            )
        )

    # Geplante Trainings für die nächsten zwei Wochen
    monday = _monday(today)
    for week in range(3):
        base = monday + timedelta(weeks=week)
        for offset, start_t, dur, type_key, title in (
            (1, "18:30", 60, "running", "Intervalle 5×1000 m"),
            (2, "07:00", 45, "running", "Lockerer Lauf Zone 2"),
            (3, "19:30", 60, "strength_training", "Krafttraining"),
            (5, "09:00", 100, "running", "Langer Lauf"),
        ):
            d = base + timedelta(days=offset)
            if d < today:
                continue
            db.add(
                PlannedWorkout(
                    date=d,
                    start_time=start_t,
                    duration_min=dur,
                    type=type_key,
                    title=title,
                    is_demo=True,
                )
            )
    db.flush()


# ---------------------------------------------------------------- Studium

SUBJECTS = [
    {
        "name": "BGB Allgemeiner Teil",
        "short": "BGB AT",
        "color": "#38bdf8",
        "exam_in": 21,
        "exam_time": "10:00",
        "location": "Audimax",
        "topics": [
            ("Rechtsgeschäftslehre & Willenserklärung", 6, 2),
            ("Vertragsschluss: Angebot und Annahme", 5, 2),
            ("Geschäftsfähigkeit", 4, 1),
            ("Anfechtung (§§ 119 ff. BGB)", 6, 3),
            ("Stellvertretung", 7, 3),
            ("Form, Gesetzes- und Sittenwidrigkeit", 4, 2),
            ("AGB-Recht", 4, 2),
            ("Verjährung", 2, 1),
        ],
    },
    {
        "name": "Buchführung & Bilanzierung",
        "short": "BuB",
        "color": "#a3e635",
        "exam_in": 28,
        "exam_time": "14:00",
        "location": "Hörsaal H3",
        "topics": [
            ("Grundlagen, Inventur & Inventar", 3, 1),
            ("Buchungssätze & Kontenrahmen", 5, 2),
            ("Umsatzsteuer", 4, 2),
            ("Abschreibungen", 4, 2),
            ("Rückstellungen & Rechnungsabgrenzung", 5, 3),
            ("Jahresabschluss", 5, 3),
        ],
    },
    {
        "name": "Mikroökonomik",
        "short": "Mikro",
        "color": "#facc15",
        "exam_in": 35,
        "exam_time": "09:00",
        "location": "Audimax",
        "topics": [
            ("Haushaltstheorie", 5, 2),
            ("Nachfrage & Elastizitäten", 4, 2),
            ("Produktionstheorie", 5, 2),
            ("Kostenfunktionen", 4, 2),
            ("Monopol", 5, 3),
            ("Oligopol & Spieltheorie", 6, 3),
            ("Marktversagen & externe Effekte", 4, 2),
        ],
    },
    {
        "name": "Staatsorganisationsrecht",
        "short": "StaatsOrga",
        "color": "#c084fc",
        "exam_in": 49,
        "exam_time": "10:00",
        "location": "Hörsaal H2",
        "topics": [
            ("Staatsstrukturprinzipien (Art. 20 GG)", 5, 2),
            ("Demokratieprinzip & Wahlrechtsgrundsätze", 4, 2),
            ("Bundestag & Gesetzgebungsverfahren", 6, 3),
            ("Bundesrat & Föderalismus", 4, 2),
            ("Bundesverfassungsgericht & Verfahrensarten", 5, 3),
            ("Klausurtechnik Organstreit", 4, 2),
        ],
    },
    {
        "name": "Steuerrecht Grundlagen",
        "short": "StR",
        "color": "#fb7185",
        "exam_in": None,
        "exam_time": None,
        "location": "",
        "topics": [
            ("Einkommensteuer: Einkunftsarten", 5, 2),
            ("Werbungskosten & Sonderausgaben", 4, 2),
        ],
    },
]


def _seed_study(db: Session, today: date, rng: random.Random) -> dict[str, Subject]:
    subjects: dict[str, Subject] = {}
    for spec in SUBJECTS:
        s = Subject(
            name=spec["name"],
            short=spec["short"],
            color=spec["color"],
            exam_date=today + timedelta(days=spec["exam_in"]) if spec["exam_in"] else None,
            exam_time=spec["exam_time"],
            exam_location=spec["location"],
            is_demo=True,
        )
        db.add(s)
        db.flush()
        for idx, (title, hours, diff) in enumerate(spec["topics"]):
            db.add(
                Topic(
                    subject_id=s.id,
                    title=title,
                    effort_hours=hours,
                    difficulty=diff,
                    status="offen",
                    order_index=idx,
                    source="manuell",
                    is_demo=True,
                )
            )
        subjects[spec["short"]] = s
    db.flush()

    bgb = subjects["BGB AT"]
    bub = subjects["BuB"]

    # Stundenplan
    timetable = [
        (bgb, "BGB AT", "Vorlesung", 0, "10:00", "12:00", "Hörsaal H1", "Prof. Dr. Weber", 1),
        (subjects["Mikro"], "Mikroökonomik", "Vorlesung", 0, "14:00", "16:00", "Audimax", "Prof. Dr. Schmitt", 1),
        (subjects["StaatsOrga"], "Staatsorganisationsrecht", "Vorlesung", 1, "08:30", "10:00", "Hörsaal H2", "Prof. Dr. Braun", 1),
        (bgb, "BGB AT", "Übung", 1, "12:00", "13:30", "Raum 204", "Lena Hoffmann", 1),
        (bub, "Buchführung & Bilanzierung", "Vorlesung", 2, "10:00", "12:00", "Hörsaal H3", "Prof. Dr. Keller", 1),
        (subjects["Mikro"], "Mikroökonomik", "Übung", 2, "16:00", "17:30", "Raum 112", "Tim Becker", 1),
        (subjects["StaatsOrga"], "Staatsorganisationsrecht", "Vorlesung", 3, "10:00", "12:00", "Hörsaal H2", "Prof. Dr. Braun", 1),
        (bub, "Buchführung", "Tutorium", 3, "14:00", "15:30", "Raum 015", "Sarah Klein", 2),
        (subjects["StR"], "Steuerrecht Grundlagen", "Vorlesung", 4, "09:00", "10:30", "Hörsaal H1", "Prof. Dr. Lang", 1),
    ]
    for subj, title, kind, weekday, st, en, room, lecturer, interval in timetable:
        db.add(
            TimetableEntry(
                subject_id=subj.id,
                title=title,
                kind=kind,
                weekday=weekday,
                start_time=st,
                end_time=en,
                room=room,
                lecturer=lecturer,
                interval_weeks=interval,
                is_demo=True,
            )
        )
    db.flush()
    return subjects


def _seed_calendar(db: Session, today: date) -> None:
    monday = _monday(today)
    events: list[tuple[datetime, datetime, str, str, bool]] = []
    for week in range(-4, 9):
        base = monday + timedelta(weeks=week)
        events.append((datetime.combine(base + timedelta(days=1), time(14, 0)), datetime.combine(base + timedelta(days=1), time(18, 0)), "Werkstudentenjob (Kanzlei)", "Kanzlei Müller & Partner", False))
        events.append((datetime.combine(base + timedelta(days=3), time(16, 0)), datetime.combine(base + timedelta(days=3), time(19, 0)), "Werkstudentenjob (Kanzlei)", "Kanzlei Müller & Partner", False))
        events.append((datetime.combine(base + timedelta(days=2), time(19, 30)), datetime.combine(base + timedelta(days=2), time(21, 0)), "Fußball mit den Jungs", "Sportpark", False))
        events.append((datetime.combine(base + timedelta(days=4), time(13, 0)), datetime.combine(base + timedelta(days=4), time(15, 0)), "Lerngruppe BGB", "Bibliothek, Gruppenraum 3", False))
    events.append((datetime.combine(today + timedelta(days=2), time(8, 0)), datetime.combine(today + timedelta(days=2), time(8, 45)), "Zahnarzt", "Praxis Dr. Sommer", False))
    events.append((datetime.combine(today + timedelta(days=9), time.min), datetime.combine(today + timedelta(days=10), time.min), "Geburtstag Mama 🎂", "", True))
    events.append((datetime.combine(today, time(12, 30)), datetime.combine(today, time(13, 15)), "Mittagessen mit Jonas", "Mensa", False))
    for idx, (st, en, title, loc, all_day) in enumerate(events):
        db.add(
            CalendarEvent(
                google_id=f"demo-{idx}",
                calendar_id="demo",
                calendar_name="Privat (Beispiel)",
                title=title,
                start=st,
                end=en,
                all_day=all_day,
                location=loc,
                is_demo=True,
            )
        )
    db.flush()


# ---------------------------------------------------------------- Alltag

MEALS = {
    "Frühstück": [
        ("Haferflocken mit Beeren & Skyr", 520, 32, 72, 10),
        ("Vollkornbrot mit Ei & Avocado", 480, 22, 40, 24),
        ("Müsli mit Milch & Banane", 560, 20, 88, 12),
    ],
    "Mittagessen": [
        ("Mensa: Hähnchen mit Reis & Gemüse", 720, 45, 85, 18),
        ("Mensa: Vegetarische Lasagne", 780, 28, 80, 34),
        ("Pasta Bolognese", 820, 38, 105, 24),
        ("Burrito Bowl", 760, 40, 90, 22),
    ],
    "Abendessen": [
        ("Lachs mit Kartoffeln & Brokkoli", 690, 42, 55, 30),
        ("Linsen-Curry mit Reis", 650, 26, 98, 14),
        ("Wraps mit Pute & Salat", 620, 40, 58, 22),
        ("Omelett mit Brot", 560, 34, 38, 28),
    ],
    "Snack": [
        ("Proteinshake", 180, 30, 6, 3),
        ("Apfel & Nüsse", 260, 6, 22, 16),
        ("Magerquark mit Honig", 240, 26, 26, 1),
        ("Banane", 110, 1, 27, 0),
    ],
}


def _seed_daily_life(db: Session, today: date, rng: random.Random, subjects: dict[str, Subject]) -> None:
    # Mahlzeiten der letzten 21 Tage (heute nur Frühstück + Snack)
    for i in range(21, -1, -1):
        day = today - timedelta(days=i)
        types = ["Frühstück", "Snack"] if i == 0 else ["Frühstück", "Mittagessen", "Snack", "Abendessen"]
        if i and rng.random() < 0.3:
            types.append("Snack")
        for mt in types:
            name, kcal, p, c, f = rng.choice(MEALS[mt])
            factor = rng.uniform(1.0, 1.25)
            db.add(
                Meal(
                    date=day,
                    meal_type=mt,
                    name=name,
                    kcal=round(kcal * factor),
                    protein=round(p * factor),
                    carbs=round(c * factor),
                    fat=round(f * factor),
                    is_demo=True,
                )
            )

    habits = [
        ("Wasser 2,5 l", "💧", 0.85),
        ("20 Min. lesen", "📖", 0.6),
        ("Dehnen & Mobility", "🧘", 0.5),
        ("Karteikarten wiederholen", "🗂️", 0.7),
        ("Kein Handy nach 23 Uhr", "📵", 0.55),
        ("Meditation", "🧠", 0.4),
    ]
    for idx, (name, emoji, prob) in enumerate(habits):
        h = Habit(name=name, emoji=emoji, sort=idx, is_demo=True)
        db.add(h)
        db.flush()
        for i in range(150, 0, -1):
            day = today - timedelta(days=i)
            # Gewohnheiten festigen sich mit der Zeit
            p = prob + (0.12 if i < 30 else 0)
            if i <= 6 and idx in (0, 3):
                p = 1.0  # laufende Streaks
            if rng.random() < p:
                db.add(HabitLog(habit_id=h.id, date=day, is_demo=True))
        if idx == 0:
            db.add(HabitLog(habit_id=h.id, date=today, is_demo=True))

    # Fokus-Sessions (Pomodoro)
    subject_list = list(subjects.values())[:4]
    for i in range(14, 0, -1):
        day = today - timedelta(days=i)
        for _ in range(rng.randint(1, 5)):
            st = datetime.combine(day, time(rng.randint(8, 19), rng.choice([0, 15, 30, 45])))
            subj = rng.choice(subject_list)
            db.add(FocusSession(start=st, end=st + timedelta(minutes=25), minutes=25, subject_id=subj.id, is_demo=True))

    todos = [
        ("Hausarbeit BGB: Gliederung abgeben", "hoch", 2, "Uni", subjects["BGB AT"].id),
        ("Altklausur BuB 2024 rechnen", "hoch", 5, "Uni", subjects["BuB"].id),
        ("Übungsblatt 4 Mikro bearbeiten", "mittel", 3, "Uni", subjects["Mikro"].id),
        ("Karteikarten Stellvertretung schreiben", "mittel", 6, "Uni", subjects["BGB AT"].id),
        ("Stundenzettel Kanzlei einreichen", "hoch", 0, "Job", None),
        ("Rückmeldung Semesterbeitrag überweisen", "hoch", -1, "Finanzen", None),
        ("Neue Laufschuhe kaufen", "niedrig", 12, "Sport", None),
        ("Steuererklärung 2025 vorbereiten", "mittel", 20, "Finanzen", None),
        ("Geschenk für Mama besorgen", "mittel", 7, "Privat", None),
        ("Bibliotheksbücher verlängern", "niedrig", 1, "Uni", None),
    ]
    for title, prio, due, cat, subj_id in todos:
        db.add(
            Todo(
                title=title,
                priority=prio,
                due_date=today + timedelta(days=due),
                category=cat,
                subject_id=subj_id,
                is_demo=True,
            )
        )
    for title, cat, ago in (("Wohnungsschlüssel nachmachen lassen", "Privat", 3), ("Skript Mikro ausdrucken", "Uni", 5)):
        db.add(
            Todo(
                title=title,
                priority="mittel",
                category=cat,
                done=True,
                done_at=datetime.combine(today - timedelta(days=ago), time(17, 0)),
                is_demo=True,
            )
        )

    morning_q = settings_store.get(db, "journal_questions")["morgen"]
    evening_q = settings_store.get(db, "journal_questions")["abend"]
    morning_answers = [
        ["Gesunder Schlaf und ein freier Vormittag.", "BGB-Stellvertretung durcharbeiten.", "Fokussiert und ruhig."],
        ["Gutes Wetter für den Lauf.", "Übungsblatt Mikro fertig machen.", "Energiegeladen."],
        ["Meine Lerngruppe.", "Altklausur Buchführung rechnen.", "Gelassen."],
    ]
    evening_answers = [
        ["Intervalle voll durchgezogen, 3 Pomodoros geschafft.", "Anfechtung: Inhalts- vs. Erklärungsirrtum.", "Früher mit dem Lernen anfangen."],
        ["Mit Jonas gekocht, entspannter Abend.", "Grenzkosten = Ableitung der Kostenfunktion.", "Handy beim Lernen weglegen."],
        ["Übungsblatt fertig, Kanzlei-Aufgabe gut gelaufen.", "Unterschied Rückstellung vs. Verbindlichkeit.", "Nicht so spät ins Bett."],
    ]
    for i in range(12, 0, -1):
        day = today - timedelta(days=i)
        ma = rng.choice(morning_answers)
        ea = rng.choice(evening_answers)
        db.add(
            JournalEntry(
                date=day,
                kind="morgen",
                mood=rng.choice([3, 4, 4, 5]),
                answers=dict(zip(morning_q, ma)),
                text="",
                is_demo=True,
            )
        )
        if rng.random() < 0.85:
            db.add(
                JournalEntry(
                    date=day,
                    kind="abend",
                    mood=rng.choice([2, 3, 4, 4, 5]),
                    answers=dict(zip(evening_q, ea)),
                    text="Insgesamt ein produktiver Tag." if rng.random() < 0.5 else "",
                    is_demo=True,
                )
            )
    db.add(
        JournalEntry(
            date=today,
            kind="morgen",
            mood=4,
            answers=dict(zip(morning_q, morning_answers[0])),
            is_demo=True,
        )
    )
    db.flush()


# ---------------------------------------------------------------- Finanzen


def _seed_finance(db: Session, today: date, rng: random.Random) -> None:
    first = date(today.year, today.month, 1)
    months = []
    m = first
    for _ in range(12):
        months.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    for month_start in months:
        def d(day: int) -> date:
            return month_start + timedelta(days=day - 1)

        is_current = month_start == first
        limit_day = today.day if is_current else 28

        def add(day: int, amount: float, kind: str, cat: str, desc: str) -> None:
            if day <= limit_day:
                db.add(Transaction(date=d(day), amount=round(amount, 2), kind=kind, category=cat, description=desc, is_demo=True))

        add(1, 603.00, "einnahme", "Werkstudentenjob", "Gehalt Kanzlei")
        add(1, 400.00, "einnahme", "Eltern", "Unterstützung")
        add(2, 415.00, "ausgabe", "Miete & Wohnen", "Miete WG-Zimmer")
        add(3, 29.00, "ausgabe", "Mobilität", "Deutschlandticket (Semesterticket-Aufpreis)")
        add(4, 34.90, "ausgabe", "Sport", "Fitnessstudio")
        add(5, 12.99, "ausgabe", "Abos", "Spotify Premium")
        add(5, 9.99, "ausgabe", "Abos", "Cloud-Speicher")
        for day in (3, 7, 10, 14, 17, 21, 24, 27):
            add(day, rng.uniform(22, 58), "ausgabe", "Lebensmittel", rng.choice(["REWE", "Aldi", "Lidl", "Edeka"]))
        for day in (6, 13, 20, 26):
            add(day, rng.uniform(8, 38), "ausgabe", "Freizeit", rng.choice(["Kino", "Bar mit Freunden", "Pizza", "Konzertkarte"]))
        add(11, rng.uniform(15, 45), "ausgabe", "Uni & Bücher", rng.choice(["Skript & Kopien", "Lehrbuch", "Schönfelder-Ergänzung"]))
        add(15, rng.uniform(5, 30), "ausgabe", "Sonstiges", rng.choice(["Drogerie", "Friseur", "Geschenk"]))
        add(18, rng.uniform(12, 26), "ausgabe", "Mobilität", "Carsharing")
        if month_start.month in (3, 9) or rng.random() < 0.2:
            add(16, 120.0, "einnahme", "Sonstiges", "Nachhilfe")
    db.flush()


def _seed_stocks(db: Session, today: date, rng: random.Random) -> None:
    positions = [
        ("EUNL.DE", "iShares Core MSCI World", "depot", 14.5, 88.40, "EUR", 101.2),
        ("SAP.DE", "SAP SE", "depot", 4, 172.30, "EUR", 238.5),
        ("ALV.DE", "Allianz SE", "depot", 2, 245.10, "EUR", 331.0),
        ("AAPL", "Apple Inc.", "depot", 3, 185.20, "USD", 232.4),
        ("NVDA", "NVIDIA Corp.", "watchlist", 0, None, "USD", 176.8),
        ("SIE.DE", "Siemens AG", "watchlist", 0, None, "EUR", 221.3),
        ("ADS.DE", "adidas AG", "watchlist", 0, None, "EUR", 197.6),
    ]
    for sym, name, kind, qty, buy, cur, price in positions:
        db.add(
            StockPosition(
                symbol=sym,
                name=name,
                kind=kind,
                quantity=qty,
                buy_price=buy,
                buy_date=today - timedelta(days=rng.randint(120, 600)) if buy else None,
                currency=cur,
                is_demo=True,
            )
        )
        # Synthetischer Kursverlauf (1 Jahr), damit Diagramme offline funktionieren
        history = []
        value = price * rng.uniform(0.72, 0.9)
        drift = math.log(price / value) / 365
        for i in range(365, -1, -1):
            day = today - timedelta(days=i)
            if day.weekday() >= 5:
                continue
            value *= math.exp(drift + rng.gauss(0, 0.012))
            history.append([day.isoformat(), round(value, 2)])
        scale = price / history[-1][1]  # Verlauf so skalieren, dass er beim aktuellen Kurs endet
        history = [[d, round(v * scale, 2)] for d, v in history]
        prev = history[-2][1]
        existing = db.get(PriceCache, sym)
        if existing is None:
            db.add(
                PriceCache(
                    symbol=sym,
                    price=price,
                    prev_close=prev,
                    currency=cur,
                    name=name,
                    history=history,
                    source="demo",
                    updated_at=datetime(2000, 1, 1),
                )
            )
    if db.get(PriceCache, "EURUSD=X") is None:
        db.add(PriceCache(symbol="EURUSD=X", price=1.12, prev_close=1.12, currency="USD", name="EUR/USD", history=[], source="demo", updated_at=datetime(2000, 1, 1)))
    db.flush()


# ---------------------------------------------------------------- News

DEMO_NEWS = [
    ("Wirtschaft", "EZB lässt Leitzins unverändert – Inflation nähert sich Zielwert", "Die Europäische Zentralbank hält den Einlagenzins stabil. Ökonomen erwarten frühestens im Frühjahr eine weitere Senkung."),
    ("Wirtschaft", "DAX schließt nahe Rekordhoch", "Starke Quartalszahlen aus der Industrie und sinkende Anleiherenditen stützen den deutschen Leitindex."),
    ("Wirtschaft", "Ifo-Geschäftsklima hellt sich überraschend auf", "Die Stimmung in den Chefetagen verbessert sich den dritten Monat in Folge."),
    ("Recht", "BGH stärkt Verbraucherrechte bei Online-Kündigungen", "Der Kündigungsbutton muss auch bei Verträgen mit Probeabo leicht auffindbar sein, entschied der VIII. Zivilsenat."),
    ("Recht", "BVerfG: Anforderungen an Wahlrechtsreform konkretisiert", "Karlsruhe betont die Bedeutung der Wahlrechtsgleichheit – relevant für jede Staatsorga-Klausur."),
    ("Recht", "Neues Gesetz zur Digitalisierung der Justiz beschlossen", "Ab 2027 sollen Zivilverfahren weitgehend elektronisch geführt werden."),
    ("Steuern", "Grundfreibetrag steigt – was Studierende mit Nebenjob wissen müssen", "Werkstudenten profitieren: Bis zur neuen Grenze fällt keine Einkommensteuer an."),
    ("Steuern", "BMF-Schreiben zu Werbungskosten bei Erststudium", "Die Finanzverwaltung präzisiert, wann Studienkosten als Sonderausgaben gelten."),
    ("Sport", "Bundesliga: Spitzenspiel endet 2:2", "Ein spätes Tor in der Nachspielzeit sichert dem Tabellenführer einen Punkt."),
    ("Sport", "Berlin-Marathon: Streckenrekord knapp verpasst", "Bei idealen Bedingungen blieb die Siegerzeit nur Sekunden über der Bestmarke."),
]


def _seed_news(db: Session, today: date) -> None:
    feeds: dict[str, NewsFeed] = {}
    existing = {f.url for f in db.query(NewsFeed).all()}
    for name, url, cat in DEFAULT_FEEDS:
        if url in existing:
            continue
        feed = NewsFeed(name=name, url=url, category=cat, is_demo=False)
        db.add(feed)
        db.flush()
        feeds.setdefault(cat, feed)
    for idx, (cat, title, summary) in enumerate(DEMO_NEWS):
        feed = feeds.get(cat)
        if feed is None:
            continue
        db.add(
            NewsItem(
                feed_id=feed.id,
                title=title,
                link=f"https://example.org/lifeos-demo/{idx}",
                summary=summary,
                published=datetime.combine(today, time(8, 0)) - timedelta(hours=idx * 5),
                category=cat,
                is_demo=True,
            )
        )
    db.flush()
