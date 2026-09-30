"""Selbst geplante Lernblöcke: bleiben genau so stehen, werden nie verschoben."""

from datetime import date, datetime, timedelta

from sqlalchemy import create_engine, inspect, text

from app.database import add_missing_columns
from app.models import StudyBlock


def _next_weekday(offset_days: int = 3) -> date:
    return date.today() + timedelta(days=offset_days)


def _subject(c, days: int = 30, topics: str = "Anfechtung | 4\nStellvertretung | 3"):
    s = c.post("/api/study/subjects", json={"name": "BGB AT", "short": "BGB", "exam_date": (date.today() + timedelta(days=days)).isoformat()}).json()
    c.post(f"/api/study/subjects/{s['id']}/topics", json={"text": topics})
    detail = c.get(f"/api/study/subjects/{s['id']}").json()
    return s, detail["topics"]


def test_create_manual_block_exact_time_and_title(client, db):
    s, topics = _subject(client)
    day = _next_weekday()
    r = client.post(
        "/api/study/blocks",
        json={"subject_id": s["id"], "topic_id": topics[0]["id"], "date": day.isoformat(), "start_time": "10:00", "end_time": "12:30", "note": "Skript S. 1–20"},
    )
    assert r.status_code == 200, r.text
    block = r.json()["blocks"][0]
    assert block["manual"] is True
    assert block["start"] == f"{day.isoformat()}T10:00:00"
    assert block["end"] == f"{day.isoformat()}T12:30:00"
    assert block["title"] == "BGB: Anfechtung"
    assert block["note"] == "Skript S. 1–20"

    # Neu planen lässt den Block unverändert stehen
    client.post("/api/study/replan")
    db.expire_all()
    b = db.get(StudyBlock, block["id"])
    assert b is not None and b.manual
    assert b.start == datetime.fromisoformat(block["start"]) and b.end == datetime.fromisoformat(block["end"])


def test_custom_title_and_validation(client):
    s, topics = _subject(client)
    day = _next_weekday().isoformat()
    r = client.post("/api/study/blocks", json={"subject_id": s["id"], "date": day, "start_time": "09:00", "end_time": "10:00", "title": "Altklausur 2023"})
    assert r.json()["blocks"][0]["title"] == "Altklausur 2023"
    bad = client.post("/api/study/blocks", json={"subject_id": s["id"], "date": day, "start_time": "12:00", "end_time": "11:00"})
    assert bad.status_code == 400
    other = client.post("/api/study/subjects", json={"name": "Anderes Fach"}).json()
    wrong_topic = client.post("/api/study/blocks", json={"subject_id": other["id"], "topic_id": topics[0]["id"], "date": day, "start_time": "09:00", "end_time": "10:00"})
    assert wrong_topic.status_code == 400


def test_weekly_repeat(client):
    s, _ = _subject(client, days=60)
    start = _next_weekday()
    r = client.post(
        "/api/study/blocks",
        json={"subject_id": s["id"], "date": start.isoformat(), "start_time": "14:00", "end_time": "16:00", "repeat_until": (start + timedelta(days=21)).isoformat()},
    ).json()
    starts = [b["start"][:10] for b in r["blocks"]]
    assert starts == [(start + timedelta(days=7 * i)).isoformat() for i in range(4)]


def test_manual_mode_creates_no_auto_blocks_and_keeps_own(client, db):
    s, topics = _subject(client)
    assert db.query(StudyBlock).filter(StudyBlock.manual.is_(False)).count() > 0  # automatisch geplant

    r = client.post("/api/study/mode", json={"mode": "manuell", "keep_plan": False})
    assert r.status_code == 200
    db.expire_all()
    assert db.query(StudyBlock).filter(StudyBlock.status == "geplant").count() == 0

    day = _next_weekday()
    client.post("/api/study/blocks", json={"subject_id": s["id"], "topic_id": topics[1]["id"], "date": day.isoformat(), "start_time": "08:00", "end_time": "09:30"})
    db.expire_all()
    blocks = db.query(StudyBlock).filter(StudyBlock.status == "geplant").all()
    assert len(blocks) == 1 and blocks[0].manual
    ov = client.get("/api/study/overview").json()
    assert ov["plan_mode"] == "manuell"
    assert [b["title"] for b in ov["blocks"]] == ["BGB: Stellvertretung"]


def test_switch_to_manual_keeps_existing_plan(client, db):
    _subject(client)
    auto_count = db.query(StudyBlock).filter(StudyBlock.status == "geplant").count()
    assert auto_count > 0
    r = client.post("/api/study/mode", json={"mode": "manuell", "keep_plan": True}).json()
    assert r["kept"] == auto_count
    db.expire_all()
    rows = db.query(StudyBlock).filter(StudyBlock.status == "geplant").all()
    assert len(rows) == auto_count and all(b.manual for b in rows)


def test_auto_mode_plans_around_manual_block_and_counts_it(client, db):
    s, topics = _subject(client, topics="Anfechtung | 2")
    day = _next_weekday()
    # Der ganze Aufwand (2 h) wird selbst eingeplant → nichts mehr automatisch zu lernen
    client.post("/api/study/blocks", json={"subject_id": s["id"], "topic_id": topics[0]["id"], "date": day.isoformat(), "start_time": "10:00", "end_time": "12:00"})
    db.expire_all()
    auto_learn = db.query(StudyBlock).filter(StudyBlock.manual.is_(False), StudyBlock.kind == "lernen", StudyBlock.status == "geplant").count()
    assert auto_learn == 0
    # Automatische Blöcke überschneiden sich nicht mit dem eigenen Block
    manual = db.query(StudyBlock).filter(StudyBlock.manual.is_(True)).one()
    for b in db.query(StudyBlock).filter(StudyBlock.manual.is_(False), StudyBlock.status == "geplant").all():
        assert b.end <= manual.start or b.start >= manual.end
    # Wiederholungen erst nach dem eigenen Lernblock
    reviews = db.query(StudyBlock).filter(StudyBlock.kind == "wiederholung", StudyBlock.status == "geplant").all()
    assert reviews and all(r.start.date() > day for r in reviews)


def test_edit_moves_block_and_makes_it_fixed(client, db):
    s, topics = _subject(client)
    auto = db.query(StudyBlock).filter(StudyBlock.manual.is_(False), StudyBlock.status == "geplant").order_by(StudyBlock.start).first()
    new_day = _next_weekday(5)
    r = client.patch(f"/api/study/blocks/{auto.id}", json={"date": new_day.isoformat(), "start_time": "07:00", "end_time": "08:00", "topic_id": topics[1]["id"]})
    assert r.status_code == 200, r.text
    b = r.json()["block"]
    assert b["manual"] and b["start"] == f"{new_day.isoformat()}T07:00:00" and b["title"] == "BGB: Stellvertretung"
    client.post("/api/study/replan")
    db.expire_all()
    moved = db.get(StudyBlock, auto.id)
    assert moved is not None and moved.start.hour == 7


def test_past_manual_block_is_not_auto_missed_and_delete(client, db):
    s, _ = _subject(client)
    yesterday = date.today() - timedelta(days=1)
    r = client.post("/api/study/blocks", json={"subject_id": s["id"], "date": yesterday.isoformat(), "start_time": "10:00", "end_time": "11:00"}).json()
    block_id = r["blocks"][0]["id"]
    client.get("/api/study/overview")
    db.expire_all()
    assert db.get(StudyBlock, block_id).status == "geplant"  # wartet auf dein ✓ oder ✗
    assert client.delete(f"/api/study/blocks/{block_id}").json()["ok"]
    db.expire_all()
    assert db.get(StudyBlock, block_id) is None


def test_google_description_contains_note(client, db):
    from app.services.google_calendar import block_body

    s, topics = _subject(client)
    r = client.post("/api/study/blocks", json={"subject_id": s["id"], "topic_id": topics[0]["id"], "date": _next_weekday().isoformat(), "start_time": "10:00", "end_time": "11:00", "note": "Fälle 1–5"}).json()
    db.expire_all()
    body = block_body(db.get(StudyBlock, r["blocks"][0]["id"]))
    assert body["summary"] == "📚 BGB: Anfechtung"
    assert body["description"].startswith("Fälle 1–5")
    assert body["start"]["dateTime"].endswith("T10:00:00")


def test_invalid_mode_setting_rejected(client):
    assert client.put("/api/settings", json={"study_plan_mode": "chaos"}).status_code == 400
    assert client.post("/api/study/mode", json={"mode": "chaos"}).status_code == 422


def test_migration_adds_columns_to_old_database(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'alt.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE study_blocks (id INTEGER PRIMARY KEY, title VARCHAR(250))"))
        conn.execute(text("INSERT INTO study_blocks (id, title) VALUES (1, 'alt')"))
    add_missing_columns(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("study_blocks")}
    assert {"manual", "note"} <= cols
    with eng.connect() as conn:
        assert conn.execute(text("SELECT manual, note FROM study_blocks")).one() == (0, "")
