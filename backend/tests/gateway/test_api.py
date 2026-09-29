"""계약 1 — POST /api/chat 요청·응답 스키마. classify만 목이고 에이전트는 실제 스텁까지 간다."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.router import RouteResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.gateway.session.sessions", {})
    monkeypatch.setattr("app.router.classify", lambda masked_text: RouteResult(topics=["balance"]))
    return TestClient(create_app())


def test_response_has_exactly_the_contract_fields(client):
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C001", "message": "잔액 알려줘"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"type", "agent", "topic", "text", "slots", "options"}
    assert body["type"] == "answer" and body["agent"] == "balance"
    assert body["text"] == "준비 중인 기능입니다."     # 스텁까지 도달


def test_choice_is_forwarded_and_skips_routing(client, monkeypatch):
    monkeypatch.setattr("app.router.classify", lambda masked_text: pytest.fail("choice가 있으면 classify를 부르면 안 된다"))
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C002", "message": "대출문의", "choice": "loan"})
    assert res.status_code == 200
    assert res.json()["agent"] == "loan"


def test_missing_required_field_is_422(client):
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C001"})
    assert res.status_code == 422
