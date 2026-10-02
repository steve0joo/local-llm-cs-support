"""계약 3(에이전트 인터페이스, docs/ARCHITECTURE.md).

- AgentRequest·AgentReply는 계약 3의 필드 이름·순서를 그대로 가진 dataclass다.
- 세 에이전트 패키지(app.agents.balance / loan / interest)가 export하는 `agent`·`mock_router`는
  각 영역의 tests/<영역>/test_agent.py가 검사한다. 통합 순서 1단계의 스텁 테스트는 세 영역이 모두 실제 구현으로 바뀌어 지웠다.
"""
import dataclasses

from app.agents.base import Agent, AgentReply, AgentRequest


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
