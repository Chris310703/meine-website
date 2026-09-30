"""Karteikarten: Spaced Repetition, Import-Formate und API-Ablauf."""

from datetime import datetime, timedelta

from app.services import flashcards as srs

NOW = datetime(2026, 9, 30, 18, 0)


# ---------------------------------------------------------------- Spaced Repetition


def test_new_card_intervals_increase_with_grade():
    p = srs.SrsState()
    days = [srs.next_interval(p, g) for g in (1, 2, 3, 4)]
    assert days[0] == 0
    assert days[1] < days[3] and days[2] < days[3]


def test_wrong_answer_comes_back_in_minutes_and_resets():
    state = srs.SrsState(ease=2.5, interval_days=20, repetitions=4)
    new, due = srs.schedule(state, 1, NOW)
    assert due == NOW + timedelta(minutes=srs.RELEARN_MINUTES)
    assert new.repetitions == 0 and new.interval_days == 0
    assert new.lapses == 1 and new.ease < 2.5


def test_good_answers_grow_intervals():
    state = srs.SrsState()
    seen = []
    for _ in range(5):
        state, due = srs.schedule(state, 3, NOW)
        seen.append(state.interval_days)
        assert due.time() == datetime.min.time()
    assert seen[:2] == [1, 3]
    assert seen == sorted(seen) and seen[-1] > 20


def test_ease_never_below_minimum():
    state = srs.SrsState()
    for _ in range(20):
        state, _ = srs.schedule(state, 1, NOW)
    assert state.ease == srs.MIN_EASE


def test_preview_labels():
    labels = srs.preview(srs.SrsState(interval_days=40, repetitions=3))
    assert labels[1] == "10 min"
    assert set(labels) == {1, 2, 3, 4}


# ---------------------------------------------------------------- Import


def test_parse_json_nested_from_claude():
    text = """Hier sind deine Karten:
```json
{"fach": "Zivilrecht", "themen": [
  {"thema": "Vertragsschluss", "karten": [
    {"frage": "Was ist ein Angebot?", "antwort": "Empfangsbedürftige Willenserklärung"},
    {"frage": "§ 145 BGB?", "antwort": "Bindung an den Antrag"}
  ]},
  {"thema": "Anfechtung", "karten": [{"frage": "Frist § 121?", "antwort": "unverzüglich"}]}
]}
```"""
    cards = srs.parse_import(text)
    assert len(cards) == 3
    assert cards[0] == {"subject": "Zivilrecht", "topic": "Vertragsschluss", "front": "Was ist ein Angebot?", "back": "Empfangsbedürftige Willenserklärung"}
    assert cards[2]["topic"] == "Anfechtung"


def test_parse_json_flat_list_with_english_keys():
    cards = srs.parse_import('[{"front": "A", "back": "B", "topic": "T"}, {"question": "C", "answer": ["x", "y"]}]')
    assert [c["front"] for c in cards] == ["A", "C"]
    assert cards[1]["back"] == "• x\n• y"


def test_parse_qa_blocks_with_headings_and_multiline_answers():
    text = """# Fach: Steuerrecht
## Thema: Einkommensteuer
F: Welche Einkunftsarten gibt es?
A: Sieben Einkunftsarten:
a) Land- und Forstwirtschaft
b) Gewerbebetrieb

**Frage:** Was regelt § 2 EStG?
**Antwort:** Umfang der Besteuerung
"""
    cards = srs.parse_import(text)
    assert len(cards) == 2
    assert cards[0]["subject"] == "Steuerrecht" and cards[0]["topic"] == "Einkommensteuer"
    assert "b) Gewerbebetrieb" in cards[0]["back"]
    assert cards[1]["front"] == "Was regelt § 2 EStG?"


def test_parse_lines_and_markdown_table():
    assert len(srs.parse_import("Frage 1 | Antwort 1\nFrage 2\tAntwort 2\nFrage 3; Antwort 3")) == 3
    table = "| Frage | Antwort |\n|---|---|\n| Was ist BIP? | Wert aller Güter |\n| Inflation? | Preisanstieg |"
    cards = srs.parse_import(table)
    assert [c["front"] for c in cards] == ["Was ist BIP?", "Inflation?"]


def test_parse_nothing():
    assert srs.parse_import("Nur ein Satz ohne Karten.") == []


# ---------------------------------------------------------------- API


def _setup(client):
    s = client.post("/api/cards/subjects", json={"name": "Zivilrecht"}).json()
    t1 = client.post("/api/cards/topics", json={"subject_id": s["id"], "name": "Vertragsschluss"}).json()
    t2 = client.post("/api/cards/topics", json={"subject_id": s["id"], "name": "Anfechtung"}).json()
    for i in range(3):
        assert client.post("/api/cards/cards", json={"topic_id": t1["id"], "front": f"V{i}", "back": "x"}).status_code == 200
    client.post("/api/cards/cards", json={"topic_id": t2["id"], "front": "A0", "back": "y"})
    return s, t1, t2


def test_overview_and_scoped_study(client):
    s, t1, t2 = _setup(client)
    ov = client.get("/api/cards").json()
    assert ov["counts"]["neu"] == 4
    subj = ov["subjects"][0]
    assert [t["counts"]["total"] for t in subj["topics"]] == [3, 1]

    whole = client.get(f"/api/cards/study?subject_id={s['id']}").json()["cards"]
    assert len(whole) == 4
    one = client.get(f"/api/cards/study?topic_ids={t2['id']}").json()["cards"]
    assert [c["front"] for c in one] == ["A0"]
    assert set(one[0]["preview"]) == {"1", "2", "3", "4"}
    both = client.get(f"/api/cards/study?topic_ids={t1['id']},{t2['id']}&new_limit=2").json()["cards"]
    assert len(both) == 2


def test_review_schedules_and_week_stats(client):
    _, t1, _ = _setup(client)
    cards = client.get(f"/api/cards/study?topic_ids={t1['id']}").json()["cards"]
    r = client.post(f"/api/cards/cards/{cards[0]['id']}/review", json={"grade": 3}).json()
    assert r["card"]["interval_days"] == 1 and r["card"]["status"] == "lernen"
    r = client.post(f"/api/cards/cards/{cards[1]['id']}/review", json={"grade": 1}).json()
    assert r["again"] is True
    client.post(f"/api/cards/cards/{cards[2]['id']}/review", json={"grade": 4})

    # Nicht mehr fällig → im Spaced-Repetition-Modus nicht dabei, im Modus „alle“ schon
    due = client.get(f"/api/cards/study?topic_ids={t1['id']}").json()["cards"]
    assert due == []
    assert len(client.get(f"/api/cards/study?topic_ids={t1['id']}&mode=alle").json()["cards"]) == 3

    # Früh richtig beantwortet (Modus „alle“) verändert den Plan nicht
    before = client.post(f"/api/cards/cards/{cards[0]['id']}/review", json={"grade": 4, "mode": "alle"}).json()["card"]
    assert before["interval_days"] == 1

    week = client.get("/api/cards/week").json()
    assert week["totals"]["reviews"] == 4
    assert week["totals"]["correct"] == 3 and week["totals"]["wrong"] == 1
    assert week["totals"]["accuracy"] == 75
    assert sum(d["correct"] + d["wrong"] for d in week["days"]) == 4
    assert week["subjects"][0]["name"] == "Zivilrecht"
    assert week["topics"][0]["subject"] == "Zivilrecht"
    assert week["hardest"][0]["front"] == "V1"
    assert client.get("/api/cards").json()["today"]["wrong"] == 1

    review = client.get("/api/review?period=woche").json()
    assert review["current"]["cards"]["reviews"] == 4
    assert any(h["icon"] == "🗂️" for h in review["highlights"])


def test_import_preview_creates_subjects_and_skips_duplicates(client):
    s, t1, _ = _setup(client)
    text = "V0 | doppelt\nNeu 1 | x\n# Fach: VWL\n## Thema: Makro\nF: BIP?\nA: Wert aller Güter"
    preview = client.post("/api/cards/import", json={"text": text, "topic_id": t1["id"], "dry_run": True}).json()
    assert preview["count"] == 3
    assert preview["new_subjects"] == ["VWL"]
    groups = {(g["subject"], g["topic"]): g["count"] for g in preview["groups"]}
    assert groups == {("Zivilrecht", "Vertragsschluss"): 2, ("VWL", "Makro"): 1}

    done = client.post("/api/cards/import", json={"text": text, "topic_id": t1["id"]}).json()
    assert done == {"created": 2, "skipped": 1, "new_subjects": ["VWL"]}
    names = [x["name"] for x in client.get("/api/cards").json()["subjects"]]
    assert names == ["VWL", "Zivilrecht"]


def test_import_needs_subject_and_cards(client):
    assert client.post("/api/cards/import", json={"text": "ohne Karten"}).status_code == 400
    assert client.post("/api/cards/import", json={"text": "F | A"}).status_code == 400
    ok = client.post("/api/cards/import", json={"text": "F | A", "subject_name": "BWL", "topic_name": "Kosten"}).json()
    assert ok["created"] == 1


def test_delete_card_keeps_statistics(client):
    _, t1, _ = _setup(client)
    card = client.get(f"/api/cards/list?topic_id={t1['id']}").json()["cards"][0]
    client.post(f"/api/cards/cards/{card['id']}/review", json={"grade": 3})
    assert client.delete(f"/api/cards/cards/{card['id']}").status_code == 200
    assert client.get("/api/cards/week").json()["totals"]["reviews"] == 1
    reset = client.get(f"/api/cards/list?q=V1").json()["cards"]
    assert len(reset) == 1


def test_generate_without_api_key(client):
    r = client.post("/api/cards/generate", json={"text": "Ein ausreichend langer Beispieltext zum Lernen."})
    assert r.status_code == 400
    assert "Schlüssel" in r.json()["detail"]


def test_relearning_card_is_rescheduled_after_second_try(client):
    _, _, t2 = _setup(client)
    card = client.get(f"/api/cards/study?topic_ids={t2['id']}").json()["cards"][0]
    for mode in ("faellig", "alle"):
        client.post(f"/api/cards/cards/{card['id']}/review", json={"grade": 1, "mode": mode})
        again = client.post(f"/api/cards/cards/{card['id']}/review", json={"grade": 3, "mode": mode}).json()["card"]
        assert again["interval_days"] == 1 and again["repetitions"] == 1
