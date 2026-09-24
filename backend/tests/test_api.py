"""Rundumtest: Alle Seiten-Endpunkte liefern mit Beispieldaten gültige Antworten."""

from datetime import date, timedelta

import pytest


@pytest.fixture()
def demo_client(client, db, monkeypatch):
    from app import seed
    from app.services import news, stocks

    # Keine Netzwerkzugriffe im Test
    monkeypatch.setattr(stocks, "refresh_async", lambda: False)
    monkeypatch.setattr(news, "refresh_async", lambda: False)
    seed.seed_demo_data(db)
    return client


GET_ENDPOINTS = [
    "/api/health",
    "/api/today",
    "/api/settings",
    "/api/status",
    "/api/garmin/status",
    "/api/fitness/summary",
    "/api/fitness/activities?days=30",
    "/api/fitness/planned",
    "/api/sleep?days=30",
    "/api/recovery?days=30",
    "/api/calendar",
    "/api/google/status",
    "/api/timetable",
    "/api/study/overview",
    "/api/study/subjects",
    "/api/study/blocks",
    "/api/nutrition",
    "/api/habits",
    "/api/focus",
    "/api/todos?status=alle",
    "/api/journal",
    "/api/finance",
    "/api/stocks",
    "/api/stocks/history/SAP.DE?period=3m",
    "/api/news",
    "/api/news/feeds",
    "/api/review?period=woche",
    "/api/review?period=monat&offset=1",
    "/api/ai/status",
    "/api/ai/history",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoints(demo_client, path):
    r = demo_client.get(path)
    assert r.status_code == 200, r.text


def test_today_contains_all_sections(demo_client):
    d = demo_client.get("/api/today").json()
    for key in ("traffic_light", "sleep", "metrics", "agenda", "study_blocks", "todos", "habits", "nutrition"):
        assert key in d
    assert d["traffic_light"]["color"] in {"gruen", "gelb", "rot"}
    assert d["demo_active"] is True


def test_crud_flow(demo_client):
    c = demo_client
    today = date.today().isoformat()
    # To-do anlegen, erledigen, löschen
    t = c.post("/api/todos", json={"title": "Testaufgabe", "priority": "hoch", "due_date": today}).json()
    assert c.patch(f"/api/todos/{t['id']}", json={"done": True}).json()["done"] is True
    assert c.delete(f"/api/todos/{t['id']}").status_code == 200
    # Mahlzeit
    m = c.post("/api/nutrition/meals", json={"date": today, "meal_type": "Snack", "name": "Apfel", "kcal": 80}).json()
    assert c.delete(f"/api/nutrition/meals/{m['id']}").status_code == 200
    # Habit anlegen und abhaken
    h = c.post("/api/habits", json={"name": "Test-Habit", "emoji": "🧪"}).json()
    assert c.post(f"/api/habits/{h['id']}/toggle", json={}).json()["done"] is True
    # Journal
    assert c.put(f"/api/journal/day/{today}/abend", json={"mood": 5, "answers": {"Frage": "Antwort"}}).status_code == 200
    assert c.get("/api/journal?q=Antwort").json()["total"] >= 1
    # Fach mit Themen → Lernplan wird erzeugt
    s = c.post("/api/study/subjects", json={"name": "Testfach", "exam_date": (date.today() + timedelta(days=20)).isoformat()}).json()
    assert c.post(f"/api/study/subjects/{s['id']}/topics", json={"text": "Thema A | 3\nThema B | 2 | 3"}).json()["added"] == 2
    detail = c.get(f"/api/study/subjects/{s['id']}").json()
    assert len(detail["topics"]) == 2
    assert sum(t["planned_minutes"] for t in detail["topics"]) >= 300
    # Stundenplan-Eintrag
    e = c.post("/api/timetable/entries", json={"title": "Test-VL", "weekday": 2, "start_time": "08:00", "end_time": "09:30"}).json()
    assert c.delete(f"/api/timetable/entries/{e['id']}").status_code == 200
    # Geplantes Training
    w = c.post("/api/fitness/planned", json={"date": today, "start_time": "20:00", "duration_min": 45, "title": "Testlauf"}).json()
    assert c.delete(f"/api/fitness/planned/{w['id']}").status_code == 200


def test_settings_validation(demo_client):
    bad = demo_client.put("/api/settings", json={"study": {"day_start": "20:00", "day_end": "08:00"}})
    assert bad.status_code == 400
    ok = demo_client.put("/api/settings", json={"study": {"buffer_days": 3}, "kcal_goal": 2800})
    assert ok.status_code == 200
    assert ok.json()["study"]["buffer_days"] == 3
    assert ok.json()["kcal_goal"] == 2800


def test_export_and_demo_removal(demo_client):
    r = demo_client.get("/api/export?format=json")
    assert r.status_code == 200
    assert "activities" in r.json()["data"]
    assert demo_client.get("/api/export?format=csv").headers["content-type"] == "application/zip"
    assert demo_client.delete("/api/demo").status_code == 200
    assert demo_client.get("/api/fitness/activities?days=365").json() == []
    assert demo_client.get("/api/today").json()["demo_active"] is False


def test_ai_endpoints_without_key(demo_client):
    r = demo_client.post("/api/ai/chat", json={"message": "Hallo"})
    assert r.status_code == 400
    assert "API-Schlüssel" in r.json()["detail"]


def test_unknown_api_path_is_404(demo_client):
    assert demo_client.get("/api/gibtsnicht").status_code == 404
