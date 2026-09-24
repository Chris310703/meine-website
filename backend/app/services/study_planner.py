"""Lernplan-Algorithmus (ohne Datenbank, vollständig testbar).

Ablauf:
1. Freie Zeitfenster je Tag berechnen (Lernfenster minus belegte Zeiten).
2. Stoff je Thema in Lerneinheiten (max. `block_minutes`) zerlegen.
3. Tag für Tag die freien Fenster füllen:
   a) fällige Wiederholungen (verteilte Wiederholung, z. B. nach 1/3/7 Tagen),
   b) Puffertage vor der Prüfung: nur Wiederholung/Altklausuren des Fachs,
   c) neuer Stoff – das Fach mit der höchsten Dringlichkeit
      (Reststoff ÷ verbleibende Kapazität bis zur Pufferphase) gewinnt.
4. Warnungen, wenn der Stoff nicht mehr bis zur Prüfung passt.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta


@dataclass
class PlanTopic:
    id: int
    title: str
    remaining_minutes: int
    learned_on: date | None = None  # Datum, an dem der Stoff abgeschlossen wurde
    reviews_done: int = 0
    order: int = 0


@dataclass
class PlanSubject:
    id: int
    name: str
    exam_date: date
    topics: list[PlanTopic]
    label: str = ""
    study_start: date | None = None

    @property
    def short(self) -> str:
        return self.label or self.name


@dataclass
class PlannerConfig:
    day_start: time = time(8, 0)
    day_end: time = time(21, 0)
    max_minutes_per_day: int = 300
    block_minutes: int = 90
    min_block_minutes: int = 45
    break_minutes: int = 15
    buffer_days: int = 2
    review_intervals: tuple[int, ...] = (1, 3, 7)
    review_minutes: int = 45
    weekdays: frozenset[int] = frozenset(range(7))
    max_blocks_per_subject_per_day: int = 3
    max_buffer_blocks_per_day: int = 2


@dataclass
class Busy:
    start: datetime
    end: datetime
    label: str = ""


@dataclass
class PlannedBlock:
    subject_id: int
    topic_id: int | None
    start: datetime
    end: datetime
    kind: str  # lernen | wiederholung | puffer
    review_number: int
    title: str

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class PlanResult:
    blocks: list[PlannedBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unplanned_minutes: dict[int, int] = field(default_factory=dict)


@dataclass
class _Review:
    due: date
    subject: PlanSubject
    topic: PlanTopic
    number: int


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _ceil_to_quarter(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    rest = dt.minute % 15
    return dt if rest == 0 else dt + timedelta(minutes=15 - rest)


def free_intervals(day: date, busy: list[Busy], cfg: PlannerConfig, now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    """Freie Zeitfenster eines Tages innerhalb des Lernfensters."""
    start = datetime.combine(day, cfg.day_start)
    end = datetime.combine(day, cfg.day_end)
    if now is not None and now > start:
        start = _ceil_to_quarter(now)
    if start >= end:
        return []
    intervals = [(start, end)]
    for b in sorted(busy, key=lambda x: x.start):
        if b.end <= start or b.start >= end:
            continue
        next_intervals = []
        for s, e in intervals:
            if b.end <= s or b.start >= e:
                next_intervals.append((s, e))
                continue
            if b.start > s:
                next_intervals.append((s, b.start))
            if b.end < e:
                next_intervals.append((b.end, e))
        intervals = next_intervals
    min_len = min(cfg.min_block_minutes, cfg.review_minutes)
    return [(s, e) for s, e in intervals if _minutes(e - s) >= min_len]


def split_units(total_minutes: int, cfg: PlannerConfig) -> list[int]:
    """Teilt Stoff in gleich große Einheiten ≤ block_minutes (auf 5 Minuten gerundet)."""
    if total_minutes <= 0:
        return []
    n = max(1, math.ceil(total_minutes / cfg.block_minutes))
    base = int(5 * math.ceil(total_minutes / n / 5))
    units = []
    left = total_minutes
    for _ in range(n):
        u = min(base, left)
        if u > 0:
            units.append(u)
        left -= u
    return units


def plan(
    subjects: list[PlanSubject],
    busy: list[Busy],
    cfg: PlannerConfig,
    now: datetime,
    used_minutes_by_day: dict[date, int] | None = None,
) -> PlanResult:
    result = PlanResult()
    today = now.date()
    subjects = [s for s in subjects if s.exam_date and s.exam_date > today]
    if not subjects:
        return result
    used_fixed = dict(used_minutes_by_day or {})
    exam_days = {s.exam_date for s in subjects}
    last_day = max(s.exam_date for s in subjects) - timedelta(days=1)

    # Belegte Zeiten nach Tag gruppieren
    busy_by_day: dict[date, list[Busy]] = {}
    for b in busy:
        d = b.start.date()
        while d <= b.end.date():
            busy_by_day.setdefault(d, []).append(b)
            d += timedelta(days=1)

    days: list[date] = []
    d = today
    while d <= last_day:
        days.append(d)
        d += timedelta(days=1)

    free: dict[date, list[tuple[datetime, datetime]]] = {}
    capacity: dict[date, int] = {}
    for d in days:
        if d.weekday() not in cfg.weekdays or d in exam_days:
            free[d], capacity[d] = [], 0
            continue
        intervals = free_intervals(d, busy_by_day.get(d, []), cfg, now if d == today else None)
        free[d] = intervals
        total = sum(_minutes(e - s) for s, e in intervals)
        capacity[d] = max(0, min(total, cfg.max_minutes_per_day - used_fixed.get(d, 0)))

    def buffer_start(s: PlanSubject) -> date:
        return s.exam_date - timedelta(days=max(0, cfg.buffer_days))

    def capacity_until(d: date, until: date) -> int:
        return sum(capacity[x] for x in days if d <= x < until)

    # Warteschlangen mit Lerneinheiten je Fach
    queues: dict[int, deque[tuple[PlanTopic, int]]] = {}
    topic_left: dict[int, int] = {}
    reviews: list[_Review] = []
    for s in subjects:
        q: deque[tuple[PlanTopic, int]] = deque()
        for t in sorted(s.topics, key=lambda x: x.order):
            if t.remaining_minutes > 0:
                for u in split_units(t.remaining_minutes, cfg):
                    q.append((t, u))
                topic_left[t.id] = t.remaining_minutes
            elif t.learned_on is not None:
                # Offene Wiederholungen; verspätete werden nachgezogen, ohne sich zu stapeln
                prev: date | None = None
                for k in range(t.reviews_done, len(cfg.review_intervals)):
                    due = t.learned_on + timedelta(days=cfg.review_intervals[k])
                    if prev is None:
                        due = max(due, today)
                    else:
                        gap = max(1, cfg.review_intervals[k] - cfg.review_intervals[k - 1])
                        due = max(due, prev + timedelta(days=gap))
                    prev = due
                    if due < s.exam_date:
                        reviews.append(_Review(due, s, t, k + 1))
        queues[s.id] = q

    overflow_used: set[int] = set()

    def schedule_reviews(s: PlanSubject, t: PlanTopic, learned: date) -> None:
        added = False
        for k, interval in enumerate(cfg.review_intervals):
            due = learned + timedelta(days=interval)
            if due < s.exam_date:
                reviews.append(_Review(due, s, t, k + 1))
                added = True
        last_chance = s.exam_date - timedelta(days=1)
        if not added and learned < last_chance:
            reviews.append(_Review(last_chance, s, t, 1))

    for d in days:
        if not free[d]:
            continue
        used = used_fixed.get(d, 0)
        per_subject: Counter[int] = Counter()
        buffer_blocks: Counter[int] = Counter()
        reviewed_today: set[int] = set()
        last_subject: int | None = None

        for interval_start, interval_end in free[d]:
            cursor = interval_start
            while True:
                limit = min(_minutes(interval_end - cursor), cfg.max_minutes_per_day - used)
                if limit < min(cfg.min_block_minutes, cfg.review_minutes):
                    break
                placed = _choose_and_place(
                    d, cursor, limit, subjects, queues, topic_left, reviews, per_subject,
                    buffer_blocks, reviewed_today, last_subject, cfg, buffer_start,
                    capacity_until, schedule_reviews, overflow_used, result,
                )
                if placed is None:
                    break
                used += placed.minutes
                per_subject[placed.subject_id] += 1
                last_subject = placed.subject_id
                cursor = placed.end + timedelta(minutes=cfg.break_minutes)
                if cursor >= interval_end:
                    break

    # Warnungen
    for s in subjects:
        left = sum(u for _, u in queues[s.id])
        if left > 0:
            result.unplanned_minutes[s.id] = left
            result.warnings.append(
                f"{s.name}: {left / 60:.1f} h Stoff passen nicht mehr bis zur Prüfung am "
                f"{s.exam_date.strftime('%d.%m.%Y')}. Gib mehr Lernzeit frei oder kürze Themen.".replace(".0 h", " h")
            )
        elif s.id in overflow_used:
            result.warnings.append(
                f"{s.name}: Der Stoff reicht bis in die Puffertage vor der Prüfung hinein."
            )
    result.blocks.sort(key=lambda b: b.start)
    return result


def _choose_and_place(
    d, cursor, limit, subjects, queues, topic_left, reviews, per_subject, buffer_blocks,
    reviewed_today, last_subject, cfg, buffer_start, capacity_until, schedule_reviews,
    overflow_used, result,
) -> PlannedBlock | None:
    def allowed(sid: int) -> bool:
        return per_subject[sid] < cfg.max_blocks_per_subject_per_day

    # a) fällige Wiederholungen
    if limit >= cfg.review_minutes:
        pending_numbers: dict[int, int] = {}
        for r in reviews:
            pending_numbers[r.topic.id] = min(pending_numbers.get(r.topic.id, r.number), r.number)
        due = [
            r for r in reviews
            if r.due <= d
            and r.subject.exam_date > d
            and allowed(r.subject.id)
            and r.topic.id not in reviewed_today
            and r.number == pending_numbers[r.topic.id]
        ]
        if due:
            due.sort(key=lambda r: (r.subject.exam_date, r.due, r.number))
            r = due[0]
            reviews.remove(r)
            reviewed_today.add(r.topic.id)
            # Folgende Wiederholungen desselben Themas frühestens nach ihrem Abstand
            for other in reviews:
                if other.topic.id == r.topic.id and other.number > r.number:
                    gap = cfg.review_intervals[other.number - 1] - cfg.review_intervals[r.number - 1]
                    other.due = max(other.due, d + timedelta(days=max(1, gap)))
            block = PlannedBlock(
                r.subject.id, r.topic.id, cursor, cursor + timedelta(minutes=cfg.review_minutes),
                "wiederholung", r.number, f"Wiederholung {r.number}: {r.topic.title}",
            )
            result.blocks.append(block)
            return block

    # b) Pufferphase: Stoff ist durch → Altklausuren & Gesamtwiederholung
    for s in sorted(subjects, key=lambda x: x.exam_date):
        if buffer_start(s) <= d < s.exam_date and not queues[s.id] and allowed(s.id):
            if buffer_blocks[s.id] >= cfg.max_buffer_blocks_per_day:
                continue
            minutes = min(cfg.block_minutes, limit)
            if minutes < cfg.min_block_minutes:
                continue
            buffer_blocks[s.id] += 1
            block = PlannedBlock(
                s.id, None, cursor, cursor + timedelta(minutes=minutes), "puffer", 0,
                f"Prüfungsvorbereitung {s.short}: Altklausur & Wiederholung",
            )
            result.blocks.append(block)
            return block

    # c) neuer Stoff nach Dringlichkeit
    candidates = [
        s for s in subjects
        if queues[s.id] and d < buffer_start(s) and (s.study_start is None or d >= s.study_start)
    ]
    overflow = False
    if not candidates:
        candidates = [s for s in subjects if queues[s.id] and d < s.exam_date and (s.study_start is None or d >= s.study_start)]
        overflow = True
    if not candidates:
        return None
    permitted = [s for s in candidates if allowed(s.id)]
    if permitted:
        candidates = permitted

    def urgency(s: PlanSubject) -> tuple[float, int]:
        left = sum(u for _, u in queues[s.id])
        until = buffer_start(s) if not overflow else s.exam_date
        cap = capacity_until(d, until)
        score = left / cap if cap > 0 else float("inf")
        if s.id == last_subject and len(candidates) > 1:
            score *= 0.75
        return (score, -s.exam_date.toordinal())

    s = max(candidates, key=urgency)
    topic, unit = queues[s.id][0]
    if unit > limit:
        if limit < cfg.min_block_minutes:
            return None
        minutes = int(limit // 5 * 5)
        queues[s.id][0] = (topic, unit - minutes)
    else:
        minutes = unit
        queues[s.id].popleft()
    topic_left[topic.id] -= minutes
    if overflow:
        overflow_used.add(s.id)
    block = PlannedBlock(
        s.id, topic.id, cursor, cursor + timedelta(minutes=minutes), "lernen", 0,
        f"{s.short}: {topic.title}",
    )
    result.blocks.append(block)
    if topic_left[topic.id] <= 0:
        schedule_reviews(s, topic, d)
    return block
