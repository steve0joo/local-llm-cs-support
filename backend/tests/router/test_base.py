"""계약 3(에이전트 인터페이스, docs/ARCHITECTURE.md)과 통합 순서 1단계의 에이전트 스텁.

- AgentRequest·AgentReply는 계약 3의 필드 이름·순서를 그대로 가진 dataclass다.
- 세 에이전트 패키지(app.agents.balance / loan / interest)는 `agent`와 `mock_router`를 export한다.
  gateway와 main.py는 이 두 이름만 import한다.
- 스텁 `agent.handle()`은 고정 문구 "준비 중인 기능입니다."를 돌려주고 모델을 부르지 않는다.
"""
import dataclasses
import importlib

import pytest
from fastapi import APIRouter

from app.agents.base import Agent, AgentReply, AgentRequest

AREAS = ["balance", "loan", "interest"]


def _field_names(cls) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_agent_request_matches_contract_3():
    assert _field_names(AgentRequest) == ["session_id", "customer_id", "masked_text", "mask_map", "history"]
    req = AgentRequest(
        session_id="s1", customer_id="C001", masked_text="[계좌번호_1] 잔액 알려줘",
        mask_map={"[계좌번호_1]": "110-1234-5678"}, history=[],
    )
    assert req.mask_map["[계좌번호_1]"] == "110-1234-5678"


def test_agent_reply_matches_contract_3():
    assert _field_names(AgentReply) == ["text", "slots", "options"]
    reply = AgentReply(text="현재 잔액은 {{balance}}입니다.", slots={"balance": "1,234,567원"}, options=[])
    assert reply.slots == {"balance": "1,234,567원"}


def test_agent_protocol_declares_name_and_handle():
    assert "name" in Agent.__annotations__
    assert callable(Agent.handle)


@pytest.mark.parametrize("area", AREAS)
def test_stub_package_exports_agent_and_mock_router(area):
    pkg = importlib.import_module(f"app.agents.{area}")
    assert pkg.agent.name == area
    assert callable(pkg.agent.handle)
    assert isinstance(pkg.mock_router, APIRouter)
    assert pkg.mock_router.routes == []  # 빈 라우터. mock API는 각 담당이 넣는다


@pytest.mark.parametrize("area", AREAS)
def test_stub_handle_returns_fixed_message(area, monkeypatch):
    """스텁은 모델을 부르지 않는다. generate가 예외를 던져도 고정 문구가 나와야 한다."""
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: pytest.fail("스텁이 llm.generate를 호출했다"))
    pkg = importlib.import_module(f"app.agents.{area}")

    reply = pkg.agent.handle(AgentRequest(
        session_id="s1", customer_id="C001", masked_text="[계좌번호_1] 잔액 알려줘",
        mask_map={"[계좌번호_1]": "110-1234-5678"}, history=[],
    ))

    assert isinstance(reply, AgentReply)
    assert reply.text == "준비 중인 기능입니다."
    assert reply.slots == {} and reply.options == []
