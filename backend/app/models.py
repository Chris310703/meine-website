"""Datenbanktabellen der Life-OS-App."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


class DemoMixin:
    """Markiert Beispieldaten, damit sie sich gezielt wieder löschen lassen."""

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


# ---------------------------------------------------------------- Einstellungen


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[object] = mapped_column(JSON, nullable=True)


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="läuft")
    message: Mapped[str] = mapped_column(Text, default="")
    items: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- Garmin-Daten


class Activity(DemoMixin, Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    garmin_id: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(40), default="other")
    name: Mapped[str] = mapped_column(String(200), default="")
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    aerobic_te: Mapped[float | None] = mapped_column(Float, nullable=True)
    anaerobic_te: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    vo2max: Mapped[float | None] = mapped_column(Float, nullable=True)
    z1_s: Mapped[float] = mapped_column(Float, default=0)
    z2_s: Mapped[float] = mapped_column(Float, default=0)
    z3_s: Mapped[float] = mapped_column(Float, default=0)
    z4_s: Mapped[float] = mapped_column(Float, default=0)
    z5_s: Mapped[float] = mapped_column(Float, default=0)


class DailyMetrics(DemoMixin, Base):
    __tablename__ = "daily_metrics"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_goal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    calories_active: Mapped[float | None] = mapped_column(Float, nullable=True)
    calories_bmr: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_wake: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_charged: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_drained: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_last_night: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_weekly_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_baseline_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_baseline_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    training_readiness: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_readiness_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recovery_time_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    acute_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    chronic_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    acwr: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vo2max: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SleepRecord(DemoMixin, Base):
    __tablename__ = "sleep"

    date: Mapped[date] = mapped_column(Date, primary_key=True)  # Datum des Aufwachens
    sleep_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sleep_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    deep_s: Mapped[float] = mapped_column(Float, default=0)
    light_s: Mapped[float] = mapped_column(Float, default=0)
    rem_s: Mapped[float] = mapped_column(Float, default=0)
    awake_s: Mapped[float] = mapped_column(Float, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_qualifier: Mapped[str | None] = mapped_column(String(30), nullable=True)
    avg_hrv: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[float | None] = mapped_column(Float, nullable=True)


class PlannedWorkout(DemoMixin, Base):
    """Geplante Trainingseinheit – blockiert Lernzeit und landet im Google-Kalender."""

    __tablename__ = "planned_workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str] = mapped_column(String(5), default="18:00")  # HH:MM
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    type: Mapped[str] = mapped_column(String(40), default="running")
    title: Mapped[str] = mapped_column(String(200), default="Training")
    notes: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    google_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    google_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------- Studium


class Subject(DemoMixin, Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    short: Mapped[str] = mapped_column(String(20), default="")
    color: Mapped[str] = mapped_column(String(9), default="#22d3ee")
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exam_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    exam_location: Mapped[str] = mapped_column(String(120), default="")
    study_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    topics: Mapped[list[Topic]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="Topic.order_index"
    )


class Topic(DemoMixin, Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    effort_hours: Mapped[float] = mapped_column(Float, default=2.0)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)  # 1 leicht – 3 schwer
    status: Mapped[str] = mapped_column(String(20), default="offen")  # offen | in_arbeit | fertig
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="manuell")  # manuell | ki

    subject: Mapped[Subject] = relationship(back_populates="topics")


class StudyDocument(DemoMixin, Base):
    __tablename__ = "study_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer, default=0)
    text_chars: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    topics_extracted: Mapped[bool] = mapped_column(Boolean, default=False)


class StudyBlock(DemoMixin, Base):
    __tablename__ = "study_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(20), default="lernen")  # lernen | wiederholung | puffer
    review_number: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="geplant")  # geplant | erledigt | verpasst
    title: Mapped[str] = mapped_column(String(250), default="")
    google_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    google_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    subject: Mapped[Subject] = relationship()
    topic: Mapped[Topic | None] = relationship()


class TimetableEntry(DemoMixin, Base):
    __tablename__ = "timetable"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(30), default="Vorlesung")
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Montag
    start_time: Mapped[str] = mapped_column(String(5))  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5))
    room: Mapped[str] = mapped_column(String(80), default="")
    lecturer: Mapped[str] = mapped_column(String(120), default="")
    interval_weeks: Mapped[int] = mapped_column(Integer, default=1)  # 1 = wöchentlich, 2 = 14-tägig
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)

    subject: Mapped[Subject | None] = relationship()


class CalendarEvent(Base):
    """Zwischenspeicher für gelesene Google-Termine."""

    __tablename__ = "calendar_events"
    __table_args__ = (UniqueConstraint("calendar_id", "google_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    google_id: Mapped[str] = mapped_column(String(250))
    calendar_id: Mapped[str] = mapped_column(String(250))
    calendar_name: Mapped[str] = mapped_column(String(250), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str] = mapped_column(String(300), default="")
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class GoogleDeletion(Base):
    """Warteschlange: Termine, die im Lernplan-Kalender gelöscht werden müssen."""

    __tablename__ = "google_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_event_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FocusSession(DemoMixin, Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    minutes: Mapped[float] = mapped_column(Float)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    study_block_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_blocks.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")

    subject: Mapped[Subject | None] = relationship()


# ---------------------------------------------------------------- Alltag


class Meal(DemoMixin, Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(30), default="Snack")
    name: Mapped[str] = mapped_column(String(200))
    kcal: Mapped[float] = mapped_column(Float, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0)
    carbs: Mapped[float] = mapped_column(Float, default=0)
    fat: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Habit(DemoMixin, Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    emoji: Mapped[str] = mapped_column(String(16), default="✅")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class HabitLog(DemoMixin, Base):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)


class Todo(DemoMixin, Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    notes: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(10), default="mittel")  # hoch | mittel | niedrig
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), default="")
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    subject: Mapped[Subject | None] = relationship()


class JournalEntry(DemoMixin, Base):
    __tablename__ = "journal"
    __table_args__ = (UniqueConstraint("date", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # morgen | abend
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------------------------------------------------------- Finanzen


class Transaction(DemoMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)  # immer positiv
    kind: Mapped[str] = mapped_column(String(10))  # einnahme | ausgabe
    category: Mapped[str] = mapped_column(String(60), default="Sonstiges")
    description: Mapped[str] = mapped_column(String(250), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StockPosition(DemoMixin, Base):
    __tablename__ = "stock_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(150), default="")
    kind: Mapped[str] = mapped_column(String(12), default="depot")  # depot | watchlist
    quantity: Mapped[float] = mapped_column(Float, default=0)
    buy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(5), default="EUR")
    notes: Mapped[str] = mapped_column(Text, default="")


class PriceCache(Base):
    __tablename__ = "price_cache"

    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(5), nullable=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    history: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [[datum, schluss], ...]
    source: Mapped[str] = mapped_column(String(20), default="yfinance")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------- News


class NewsFeed(DemoMixin, Base):
    __tablename__ = "news_feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(60), default="Allgemein")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class NewsItem(DemoMixin, Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("news_feeds.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(1000), unique=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(60), default="Allgemein")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    feed: Mapped[NewsFeed] = relationship()


# ---------------------------------------------------------------- KI


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation: Mapped[str] = mapped_column(String(40), index=True, default="standard")
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
