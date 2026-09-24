"""Tests der Claude-Anbindung mit simulierter API (kein echter Schlüssel nötig)."""

import json

import pytest

from app import config
from app.services import ai_tools, claude_ai


def _message(content, stop_reason="end_turn"):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": config.CLAUDE_MODEL,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture()
def fake_api(monkeypatch):
    import anthropic
    import httpx2

    requests = []
    replies = []

    def handler(request):
        body = json.loads(request.content)
        requests.append({"headers": dict(request.headers), "body": body, "path": request.url.path})
        return httpx2.Response(200, json=replies.pop(0))

    client = anthropic.Anthropic(api_key="test-key", http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)), max_retries=0)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(claude_ai, "_client", client)
    return requests, replies


def test_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(claude_ai, "_client", None)
    assert not claude_ai.available()
    with pytest.raises(claude_ai.ClaudeUnavailable):
        claude_ai.client()


def test_tool_loop_executes_tools_and_returns_text(fake_api):
    requests, replies = fake_api
    replies.append(_message([{"type": "tool_use", "id": "toolu_1", "name": "heute_ueberblick", "input": {}}], "tool_use"))
    replies.append(_message([{"type": "text", "text": "Heute ist ein grüner Tag – ab ins Intervalltraining!"}]))
    calls = []

    def execute(name, args):
        calls.append(name)
        return {"ampel": "gruen"}

    result = claude_ai.run_with_tools("System", [{"role": "user", "content": "Soll ich heute hart trainieren?"}], ai_tools.TOOLS, execute)
    assert result["text"].startswith("Heute ist ein grüner Tag")
    assert calls == ["heute_ueberblick"]
    assert len(requests) == 2
    first = requests[0]
    assert first["path"].endswith("/v1/messages")
    assert first["body"]["model"] == config.CLAUDE_MODEL
    assert first["body"]["output_config"]["effort"] == claude_ai.EFFORT
    assert {t["name"] for t in first["body"]["tools"]} == {t["name"] for t in ai_tools.TOOLS}
    if config.CLAUDE_MODEL.startswith("claude-opus-5"):
        assert first["body"]["fallbacks"] == "default"
        assert claude_ai.FALLBACK_BETA in first["headers"]["anthropic-beta"]
    # Zweite Anfrage enthält das Werkzeugergebnis
    last_user = requests[1]["body"]["messages"][-1]
    assert last_user["role"] == "user"
    assert last_user["content"][0]["type"] == "tool_result"
    assert json.loads(last_user["content"][0]["content"]) == {"ampel": "gruen"}


def test_tool_errors_are_reported_to_claude(fake_api):
    requests, replies = fake_api
    replies.append(_message([{"type": "tool_use", "id": "toolu_1", "name": "finanzen", "input": {"monat": "kaputt"}}], "tool_use"))
    replies.append(_message([{"type": "text", "text": "Dazu habe ich keine Daten gefunden."}]))

    def execute(name, args):
        raise ValueError("Monat ungültig")

    result = claude_ai.run_with_tools("System", [{"role": "user", "content": "Finanzen?"}], ai_tools.TOOLS, execute)
    assert "keine Daten" in result["text"]
    tool_result = requests[1]["body"]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_refusal_is_reported(fake_api):
    _, replies = fake_api
    replies.append(_message([], "refusal"))
    with pytest.raises(claude_ai.ClaudeError):
        claude_ai.run_with_tools("System", [{"role": "user", "content": "x"}], ai_tools.TOOLS, lambda n, a: None)


def test_extract_topics_uses_structured_output(fake_api):
    requests, replies = fake_api
    topics = {
        "topics": [
            {"title": "Willenserklärung", "effort_hours": 5, "difficulty": 2, "summary": "Tatbestand und Auslegung."},
            {"title": "Anfechtung", "effort_hours": 40, "difficulty": 7, "summary": "Irrtum, Täuschung, Drohung."},
        ]
    }
    replies.append(_message([{"type": "text", "text": json.dumps(topics)}]))
    result = claude_ai.extract_topics("BGB AT", [("skript.pdf", "[Seite 1]\nDie Willenserklärung …"), ("leer.pdf", "")], "15.10.2026")
    assert [t["title"] for t in result["topics"]] == ["Willenserklärung", "Anfechtung"]
    assert result["topics"][1]["effort_hours"] == 20  # auf sinnvolle Obergrenze begrenzt
    assert result["topics"][1]["difficulty"] == 3
    assert "leer.pdf" in result["note"]
    body = requests[0]["body"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "skript.pdf" in body["messages"][0]["content"]


def test_extract_topics_without_text_fails(fake_api):
    with pytest.raises(claude_ai.ClaudeError):
        claude_ai.extract_topics("BGB", [("scan.pdf", "  ")])


def test_ai_tools_run_on_empty_database(db):
    for tool in ai_tools.TOOLS:
        result = ai_tools.execute(db, tool["name"], {})
        json.dumps(result, default=str)  # muss serialisierbar sein
    assert "fehler" in ai_tools.execute(db, "gibt_es_nicht", {})
