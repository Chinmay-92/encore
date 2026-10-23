import json

from fastapi.testclient import TestClient

from app.main import app


def parse(body: str):
    return [json.loads(chunk[6:]) for chunk in body.split("\n\n") if chunk.startswith("data: ")]


def test_health_and_residents(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h == {"ok": True, "qloo": "mock", "agent": "scripted", "model": None}
        assert len(c.get("/api/residents").json()) == 3
        assert "Encore" in c.get("/").text


def test_plan_stream_end_to_end(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as c:
        residents = c.get("/api/residents").json()
        r = c.post("/api/plan", json={"residents": residents[:2], "session": "group", "location": "Hove"})
        assert r.status_code == 200
        events = parse(r.text)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "done" and events[-1]["qloo_calls"] > 5
        assert any(e["type"] == "plan" for e in events)


def test_plan_validation(monkeypatch):
    with TestClient(app) as c:
        assert c.post("/api/plan", json={"residents": []}).status_code == 422
