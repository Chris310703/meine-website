"""Tests für den Lernplan-Algorithmus."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from app.services.study_planner import (
    Busy,
    PlannerConfig,
    PlanSubject,
    PlanTopic,
    free_intervals,
    plan,
    split_units,
)

MONDAY = date(2026, 10, 5)
NOW = datetime.combine(MONDAY, time(7, 0))


def cfg(**kw) -> PlannerConfig:
    base = dict(
        day_start=time(8, 0),
        day_end=time(20, 0),
        max_minutes_per_day=300,
        block_minutes=90,
        min_block_minutes=45,
        break_minutes=15,
        buffer_days=2,
        review_intervals=(1, 3, 7),
        review_minutes=45,
    )
    base.update(kw)
    return PlannerConfig(**base)


def subject(sid, exam_in_days, topics, name=None):
    return PlanSubject(
        id=sid,
        name=name or f"Fach {sid}",
        exam_date=MONDAY + timedelta(days=exam_in_days),
        topics=[PlanTopic(id=sid * 100 + i, title=f"T{i}", remaining_minutes=m, order=i) for i, m in enumerate(topics)],
    )


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------- Hilfsfunktionen


def test_free_intervals_respect_busy_and_now():
    busy = [Busy(datetime.combine(MONDAY, time(10)), datetime.combine(MONDAY, time(12)))]
    now = datetime.combine(MONDAY, time(8, 50))
    slots = free_intervals(MONDAY, busy, cfg(), now)
    assert slots[0][0] == datetime.combine(MONDAY, time(9, 0))  # auf Viertelstunde aufgerundet
    assert slots[0][1] == datetime.combine(MONDAY, time(10))
    assert slots[1] == (datetime.combine(MONDAY, time(12)), datetime.combine(MONDAY, time(20)))


def test_free_intervals_drop_tiny_gaps():
    busy = [
        Busy(datetime.combine(MONDAY, time(8)), datetime.combine(MONDAY, time(10))),
        Busy(datetime.combine(MONDAY, time(10, 30)), datetime.combine(MONDAY, time(20))),
    ]
    assert free_intervals(MONDAY, busy, cfg()) == []


def test_split_units_even_chunks():
    assert split_units(300, cfg()) == [75, 75, 75, 75]
    assert split_units(90, cfg()) == [90]
    assert split_units(30, cfg()) == [30]
    assert sum(split_units(245, cfg())) == 245
    assert split_units(0, cfg()) == []


# ---------------------------------------------------------------- Planung


def test_blocks_never_overlap_busy_times_or_each_other():
    busy = []
    for d in range(14):
        day = MONDAY + timedelta(days=d)
        busy.append(Busy(datetime.combine(day, time(10)), datetime.combine(day, time(12)), "Vorlesung"))
        busy.append(Busy(datetime.combine(day, time(18)), datetime.combine(day, time(19, 30)), "Training"))
    subjects = [subject(1, 14, [240, 180, 300]), subject(2, 12, [200, 200])]
    result = plan(subjects, busy, cfg(), NOW)
    assert result.blocks
    for b in result.blocks:
        assert time(8) <= b.start.time() and b.end.time() <= time(20)
        for x in busy:
            assert not overlaps(b.start, b.end, x.start, x.end), (b, x)
    ordered = sorted(result.blocks, key=lambda b: b.start)
    for a, b in zip(ordered, ordered[1:]):
        assert a.end + timedelta(minutes=15) <= b.start  # Pause eingehalten


def test_daily_limit_is_respected():
    subjects = [subject(1, 20, [900, 900])]
    result = plan(subjects, [], cfg(max_minutes_per_day=180), NOW)
    per_day = defaultdict(int)
    for b in result.blocks:
        per_day[b.start.date()] += b.minutes
    assert per_day and max(per_day.values()) <= 180


def test_all_blocks_before_exam_and_exam_day_free():
    s1 = subject(1, 6, [180, 120])
    s2 = subject(2, 10, [240])
    result = plan([s1, s2], [], cfg(), NOW)
    exam_days = {s1.exam_date, s2.exam_date}
    for b in result.blocks:
        exam = s1.exam_date if b.subject_id == 1 else s2.exam_date
        assert b.start.date() < exam
        assert b.start.date() not in exam_days


def test_no_new_material_in_buffer_days():
    s = subject(1, 12, [180, 180])
    result = plan([s], [], cfg(buffer_days=3), NOW)
    buffer_start = s.exam_date - timedelta(days=3)
    learn = [b for b in result.blocks if b.kind == "lernen"]
    assert learn and all(b.start.date() < buffer_start for b in learn)
    buffer_blocks = [b for b in result.blocks if b.start.date() >= buffer_start]
    assert buffer_blocks, "Puffertage sollen für Wiederholung/Altklausuren genutzt werden"
    assert {b.kind for b in buffer_blocks} <= {"wiederholung", "puffer"}
    assert not result.warnings


def test_spaced_repetition_after_topic_is_finished():
    s = subject(1, 20, [90])
    result = plan([s], [], cfg(), NOW)
    learn = [b for b in result.blocks if b.kind == "lernen"]
    reviews = sorted((b for b in result.blocks if b.kind == "wiederholung"), key=lambda b: b.start)
    assert len(learn) == 1
    learned_on = learn[0].start.date()
    assert [r.review_number for r in reviews] == [1, 2, 3]
    assert [(r.start.date() - learned_on).days for r in reviews] == [1, 3, 7]
    assert all(r.minutes == 45 for r in reviews)


def test_reviews_are_skipped_when_exam_is_too_close():
    s = subject(1, 3, [90])
    result = plan([s], [], cfg(buffer_days=1), NOW)
    reviews = [b for b in result.blocks if b.kind == "wiederholung"]
    assert reviews and all(r.start.date() < s.exam_date for r in reviews)


def test_overdue_reviews_for_learned_topics_are_not_stacked():
    s = PlanSubject(
        id=1,
        name="BGB",
        exam_date=MONDAY + timedelta(days=30),
        topics=[PlanTopic(id=1, title="Willenserklärung", remaining_minutes=0, learned_on=MONDAY - timedelta(days=10), reviews_done=1)],
    )
    result = plan([s], [], cfg(), NOW)
    reviews = sorted((b for b in result.blocks if b.kind == "wiederholung"), key=lambda b: b.start)
    assert [r.review_number for r in reviews] == [2, 3]
    # verspätete Wiederholung heute, die nächste frühestens 4 Tage später
    assert reviews[0].start.date() == MONDAY
    assert (reviews[1].start.date() - reviews[0].start.date()).days >= 4


def test_warning_when_not_enough_time():
    s = subject(1, 3, [900, 900], name="Mikroökonomik")
    result = plan([s], [], cfg(max_minutes_per_day=120), NOW)
    assert result.unplanned_minutes.get(1, 0) > 0
    assert any("Mikroökonomik" in w and "passen nicht" in w for w in result.warnings)


def test_uses_buffer_days_when_material_does_not_fit_before():
    s = subject(1, 4, [400], name="BuB")
    result = plan([s], [], cfg(max_minutes_per_day=180, buffer_days=2), NOW)
    assert not result.unplanned_minutes
    assert any("Puffertage" in w for w in result.warnings)
    buffer_start = s.exam_date - timedelta(days=2)
    assert any(b.kind == "lernen" and b.start.date() >= buffer_start for b in result.blocks)


def test_earlier_exam_gets_priority():
    early = subject(1, 5, [360])
    late = subject(2, 40, [360])
    result = plan([early, late], [], cfg(max_minutes_per_day=180), NOW)
    first_day = min(b.start.date() for b in result.blocks)
    first_blocks = [b for b in result.blocks if b.start.date() == first_day and b.kind == "lernen"]
    assert first_blocks[0].subject_id == 1
    early_learn = [b for b in result.blocks if b.subject_id == 1 and b.kind == "lernen"]
    assert sum(b.minutes for b in early_learn) == 360
    assert not result.unplanned_minutes


def test_subjects_are_interleaved_within_a_day():
    a = subject(1, 20, [600])
    b = subject(2, 21, [600])
    result = plan([a, b], [], cfg(), NOW)
    day_blocks = sorted((x for x in result.blocks if x.start.date() == MONDAY), key=lambda x: x.start)
    assert len({x.subject_id for x in day_blocks}) == 2


def test_weekday_selection_is_respected():
    s = subject(1, 21, [1200])
    result = plan([s], [], cfg(weekdays=frozenset({0, 1, 2, 3, 4})), NOW)
    assert all(b.start.weekday() < 5 for b in result.blocks)


def test_study_start_date_is_respected():
    s = subject(1, 21, [600])
    s.study_start = MONDAY + timedelta(days=7)
    result = plan([s], [], cfg(), NOW)
    assert all(b.start.date() >= s.study_start for b in result.blocks if b.kind == "lernen")


def test_used_minutes_reduce_capacity_today():
    s = subject(1, 10, [900])
    result = plan([s], [], cfg(max_minutes_per_day=180), NOW, used_minutes_by_day={MONDAY: 180})
    assert not any(b.start.date() == MONDAY for b in result.blocks)


def test_past_exams_are_ignored():
    s = subject(1, -1, [120])
    assert plan([s], [], cfg(), NOW).blocks == []


# ---------------------------------------------------------------- mit Datenbank


def test_replan_reschedules_missed_blocks(db):
    from app.models import StudyBlock, Subject, Topic
    from app.services import study_service

    today = date.today()
    s = Subject(name="Staatsrecht", short="StR", exam_date=today + timedelta(days=14))
    db.add(s)
    db.flush()
    t = Topic(subject_id=s.id, title="Bundestag", effort_hours=3)
    db.add(t)
    db.flush()
    yesterday = datetime.combine(today - timedelta(days=1), time(9))
    db.add(StudyBlock(subject_id=s.id, topic_id=t.id, start=yesterday, end=yesterday + timedelta(minutes=90), kind="lernen", status="geplant", title="alt"))
    db.commit()

    now = datetime.combine(today, time(7))
    result = study_service.replan(db, now)
    assert result["missed"] == 1
    old = db.query(StudyBlock).filter(StudyBlock.start == yesterday).one()
    assert old.status == "verpasst"
    future_learn = db.query(StudyBlock).filter(StudyBlock.status == "geplant", StudyBlock.kind == "lernen").all()
    # Der verpasste Stoff (3 h) ist vollständig neu eingeplant
    assert sum(int((b.end - b.start).total_seconds() // 60) for b in future_learn) == 180
    assert all(b.start >= now for b in future_learn)


def test_done_blocks_count_as_progress(db):
    from app.models import StudyBlock, Subject, Topic
    from app.services import study_service

    today = date.today()
    s = Subject(name="Mikro", short="Mikro", exam_date=today + timedelta(days=20))
    db.add(s)
    db.flush()
    t = Topic(subject_id=s.id, title="Monopol", effort_hours=3)
    db.add(t)
    db.flush()
    start = datetime.combine(today - timedelta(days=2), time(9))
    db.add(StudyBlock(subject_id=s.id, topic_id=t.id, start=start, end=start + timedelta(minutes=120), kind="lernen", status="erledigt", title="x"))
    db.commit()
    study_service.replan(db, datetime.combine(today, time(7)))
    planned = db.query(StudyBlock).filter(StudyBlock.status == "geplant", StudyBlock.kind == "lernen").all()
    assert sum(int((b.end - b.start).total_seconds() // 60) for b in planned) == 60
    overview = study_service.subject_overview(db, today)[0]
    assert overview["progress"] == 67
    assert overview["days_left"] == 20
