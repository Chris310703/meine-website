"""Trainingsplan: Standardplan, Bearbeiten, Trainingstagebuch und Progression."""

from datetime import date, timedelta

from app.models import PlanExercise, TrainingSession
from app.services import training


def _plan(client):
    r = client.get("/api/training/plan")
    assert r.status_code == 200, r.text
    return r.json()


def _session(plan, title):
    return next(s for d in plan["days"] for s in d["sessions"] if s["title"] == title)


def test_default_plan_matches_week(client):
    p = _plan(client)
    kinds = {d["label"]: [s["kind"] for s in d["sessions"]] for d in p["days"]}
    assert kinds["Mittwoch"] == ["ruhe"] and kinds["Freitag"] == ["ruhe"]  # zwei Ruhetage
    assert "fussball" in kinds["Dienstag"] and "fussball" in kinds["Donnerstag"] and kinds["Sonntag"] == ["fussball"]
    assert kinds["Montag"] == ["kraft"] and kinds["Samstag"] == ["kraft"]
    upper_a = _session(p, "Oberkörper A – Drücken")
    assert upper_a["exercises"][0]["name"] == "Bankdrücken (Langhantel)"
    assert upper_a["exercises"][0]["sets"] == 4 and upper_a["exercises"][0]["reps"] == "6–8"
    # Keine Übung braucht Maschinen oder Kabelzug
    names = " ".join(e["name"].lower() for d in p["days"] for s in d["sessions"] for e in s["exercises"])
    assert "kabel" not in names and "maschine" not in names and "latzug" not in names
    assert p["guide"]["rules"]


def test_plan_is_seeded_only_once(client, db):
    _plan(client)
    for s in db.query(TrainingSession).all():
        db.delete(s)
    db.commit()
    p = _plan(client)
    assert all(not d["sessions"] for d in p["days"])  # gelöschter Plan kommt nicht von allein zurück
    assert client.post("/api/training/plan/reset").json()["ok"]
    assert _plan(client)["days"][0]["sessions"]


def test_edit_session_and_exercises(client):
    p = _plan(client)
    s = _session(p, "Oberkörper B – Ziehen & Rumpf")
    r = client.post(f"/api/training/sessions/{s['id']}/exercises", json={"name": "Facepulls mit Band", "sets": 3, "reps": "15", "increment_kg": 0}).json()
    assert r["rep_target"] == 15
    ex_id = r["id"]
    assert client.patch(f"/api/training/exercises/{ex_id}", json={"sets": 4, "reps": "12–15"}).json()["sets"] == 4
    ids = [e["id"] for e in client.get(f"/api/training/sessions/{s['id']}").json()["exercises"]]
    client.post(f"/api/training/sessions/{s['id']}/reorder", json={"exercise_ids": [ids[-1]] + ids[:-1]})
    first = client.get(f"/api/training/sessions/{s['id']}").json()["exercises"][0]
    assert first["name"] == "Facepulls mit Band"
    assert client.delete(f"/api/training/exercises/{ex_id}").json()["ok"]
    new = client.post("/api/training/sessions", json={"weekday": 0, "kind": "handball", "title": "Handballtraining"}).json()
    assert new["order_index"] == 1
    assert client.patch(f"/api/training/sessions/{new['id']}", json={"notes": "nur manchmal"}).json()["notes"] == "nur manchmal"
    assert client.delete(f"/api/training/sessions/{new['id']}").json()["ok"]


def _log_bench(client, session, day, weight, reps_list, notes=""):
    ex = session["exercises"][0]
    sets = [
        {"exercise_id": ex["id"], "exercise_name": ex["name"], "set_number": i + 1, "weight_kg": weight, "reps": r, "done": True}
        for i, r in enumerate(reps_list)
    ]
    r = client.post(
        "/api/training/logs",
        json={"session_id": session["id"], "date": day.isoformat(), "kind": "kraft", "notes": notes, "rating": 4, "duration_min": 62, "sets": sets},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_log_training_with_weights_notes_and_progression(client):
    p = _plan(client)
    s = _session(p, "Oberkörper A – Drücken")
    today = date.today()
    log = _log_bench(client, s, today - timedelta(days=7), 60, [8, 8, 7, 6], notes="Schulter etwas steif")
    assert log["title"] == "Oberkörper A – Drücken"
    assert log["notes"] == "Schulter etwas steif" and log["rating"] == 4
    assert log["exercises"][0]["name"] == "Bankdrücken (Langhantel)" and len(log["exercises"][0]["sets"]) == 4
    assert log["volume_kg"] == 60 * (8 + 8 + 7 + 6)

    detail = client.get(f"/api/training/sessions/{s['id']}").json()
    bench = detail["exercises"][0]
    assert bench["last"]["sets"][0]["weight_kg"] == 60
    assert bench["suggestion"]["increase"] is False and bench["suggestion"]["weight_kg"] == 60

    _log_bench(client, s, today, 60, [8, 8, 8, 8])
    bench = client.get(f"/api/training/sessions/{s['id']}").json()["exercises"][0]
    assert bench["suggestion"]["increase"] is True and bench["suggestion"]["weight_kg"] == 62.5

    prog = client.get("/api/training/progress", params={"exercise": "Bankdrücken (Langhantel)"}).json()
    assert [pt["best_weight"] for pt in prog["points"]] == [60, 60]
    assert prog["best_e1rm"] == training.estimated_1rm(60, 8)
    names = [e["name"] for e in client.get("/api/training/exercises").json()]
    assert names == ["Bankdrücken (Langhantel)"]

    plan_now = _plan(client)
    assert _session(plan_now, "Oberkörper A – Drücken")["last_log"]["date"] == today.isoformat()
    today_data = client.get("/api/today").json()["training"]
    if today.weekday() == 0:
        assert today_data["sessions"][0]["logged"] is True


def test_update_and_delete_log_skips_empty_sets(client):
    p = _plan(client)
    s = _session(p, "Unterkörper – Kraft")
    ex = s["exercises"][0]
    body = {
        "session_id": s["id"],
        "date": date.today().isoformat(),
        "kind": "kraft",
        "sets": [
            {"exercise_id": ex["id"], "exercise_name": ex["name"], "set_number": 1, "weight_kg": 80, "reps": 5},
            {"exercise_id": ex["id"], "exercise_name": ex["name"], "set_number": 2, "weight_kg": None, "reps": None},
        ],
    }
    log = client.post("/api/training/logs", json=body).json()
    assert log["sets_done"] == 1
    body["notes"] = "Kniebeugen liefen gut"
    body["sets"][1].update(weight_kg=80, reps=5)
    updated = client.put(f"/api/training/logs/{log['id']}", json=body).json()
    assert updated["sets_done"] == 2 and updated["notes"] == "Kniebeugen liefen gut"
    assert len(client.get("/api/training/logs").json()) == 1
    assert client.delete(f"/api/training/logs/{log['id']}").json()["ok"]
    assert client.get("/api/training/logs").json() == []


def test_free_training_without_plan_and_bodyweight_suggestion(client, db):
    r = client.post(
        "/api/training/logs",
        json={"date": date.today().isoformat(), "kind": "lauf", "title": "Lockerer Lauf", "notes": "5 km locker", "rating": 5},
    ).json()
    assert r["session_id"] is None and r["title"] == "Lockerer Lauf"

    ex = PlanExercise(name="Nordic Hamstring Curls", sets=3, reps="4–6", increment_kg=0)
    last = {"sets": [{"weight_kg": None, "reps": 6, "done": True}] * 3}
    sug = training.suggestion(ex, last)
    assert sug["increase"] is True and sug["weight_kg"] is None


def test_rep_target_parsing():
    assert training.rep_target("6–8") == (8, False)
    assert training.rep_target("5") == (5, False)
    assert training.rep_target("20–30 s") == (30, True)
    assert training.rep_target("max") == (None, False)
    assert training.estimated_1rm(100, 5) == round(100 * (1 + 5 / 30), 1)
    assert training.estimated_1rm(None, 5) is None


def test_validation(client):
    assert client.post("/api/training/sessions", json={"weekday": 7, "title": "x"}).status_code == 422
    assert client.post("/api/training/sessions", json={"weekday": 1, "kind": "yoga", "title": "x"}).status_code == 422
    assert client.post("/api/training/logs", json={"date": "2026-10-01", "rating": 9}).status_code == 422
    assert client.get("/api/training/progress", params={"exercise": "Gibt es nicht"}).status_code == 404
