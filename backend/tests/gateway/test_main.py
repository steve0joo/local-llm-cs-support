"""main.py — /api/chat과 세 에이전트의 mock_router를 한 앱에 등록한다."""
from fastapi import APIRouter

from app.main import create_app


def test_chat_route_is_registered():
    paths = create_app().openapi()["paths"]
    assert "post" in paths["/api/chat"]


def test_each_agent_mock_router_is_included(monkeypatch):
    mock_router = APIRouter()

    @mock_router.get("/mock/customers/{customer_id}/loans")
    def loans(customer_id: str):
        return []

    monkeypatch.setattr("app.agents.loan.mock_router", mock_router)
    paths = create_app().openapi()["paths"]
    assert "/mock/customers/{customer_id}/loans" in paths
