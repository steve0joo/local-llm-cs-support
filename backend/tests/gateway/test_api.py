"""계약 1 — POST /api/chat 요청·응답 스키마. classify와 에이전트는 목이다.

에이전트를 두면 각 영역의 답변 문구·mock 데이터·Ollama 호출에 묶인다. 여기서는 요청이 에이전트까지 닿는지만 본다.
"""
import pytest
from fastapi.testclient import TestClient

from app.agents.base import AgentReply
from app.gateway import dispatch as dispatch_module
from app.main import create_app
from app.router import RouteResult

FAKE_TEXT = "loan 답변 {{slot}}"


class FakeAgent:
    name = "loan"

    def handle(self, req):
        return AgentReply(text=FAKE_TEXT, slots={"slot": "1,234원"}, options=[])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.gateway.session.sessions", {})
    monkeypatch.setattr("app.router.classify", lambda masked_text: RouteResult(topics=["loan"]))
    monkeypatch.setitem(dispatch_module.AGENTS, "loan", FakeAgent())
    return TestClient(create_app())


def test_response_has_exactly_the_contract_fields(client):
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C001", "message": "잔액 알려줘"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"type", "agent", "topic", "text", "slots", "options"}
    assert body["type"] == "answer" and body["agent"] == "loan"
    assert body["text"] == FAKE_TEXT                    # 에이전트까지 도달
    assert body["slots"] == {"slot": "1,234원"}


def test_choice_is_forwarded_and_skips_routing(client, monkeypatch):
    monkeypatch.setattr("app.router.classify", lambda masked_text: pytest.fail("choice가 있으면 classify를 부르면 안 된다"))
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C002", "message": "대출문의", "choice": "loan"})
    assert res.status_code == 200
    assert res.json()["agent"] == "loan"


def test_missing_required_field_is_422(client):
    res = client.post("/api/chat", json={"session_id": "s1", "customer_id": "C001"})
    assert res.status_code == 422
