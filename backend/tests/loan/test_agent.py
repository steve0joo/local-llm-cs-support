"""LoanAgent.handle() (docs/agent-loan/ARCHITECTURE.md handle() 1~7단계). llm.generate는 목으로 대체한다."""
import json

import pytest

from app.agents.base import AgentRequest
from app.agents.loan.agent import agent
from app.agents.loan.mock_api import get_loans
from app.agents.loan.prompt import NO_LOAN_TEXT, fallback_text


def _req(customer_id: str, masked_text: str = "질문", history: list[dict] | None = None) -> AgentRequest:
    return AgentRequest(
        session_id="s1",
        customer_id=customer_id,
        masked_text=masked_text,
        mask_map={"[계좌번호_1]": "110-1234-5678"},
        history=history or [],
    )


def test_no_loan_does_not_call_model(monkeypatch):
    calls = []
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: calls.append((a, k)) or "무시됨")

    reply = agent.handle(_req("C001"))

    assert calls == []
    assert reply.text == NO_LOAN_TEXT
    assert reply.slots == {}
    assert reply.options == []


def test_principal_not_leaked_and_slots_correct(monkeypatch):
    captured = {}

    def fake_generate(model, messages, **options):
        captured["model"] = model
        captured["messages"] = messages
        return "만기일은 2027-03-31입니다. {{principal_remaining}} 남았습니다."

    monkeypatch.setattr("app.llm.generate", fake_generate)

    reply = agent.handle(_req("C002", "남은 원금이 얼마예요?"))

    dumped = json.dumps(captured["messages"], ensure_ascii=False)
    assert "12000000" not in dumped
    assert "12,000,000" not in dumped
    assert captured["model"] == "cs-loan"
    assert reply.slots["loan_label"] == "신용대출"
    assert reply.slots["principal_remaining"] == "12,000,000원"
    assert reply.options == []


@pytest.mark.parametrize(
    "mock_text",
    [
        "금리는 연 3.5%입니다.",
        "재직증명서가 필요합니다.",
        "{{balance}}입니다.",
        "1,200만원입니다.",
    ],
)
def test_invalid_output_falls_back_to_fixed_sentence(monkeypatch, mock_text):
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: mock_text)

    reply = agent.handle(_req("C002"))

    assert reply.text == fallback_text(get_loans("C002")[0])


def test_valid_output_passes_through(monkeypatch):
    text = "만기일은 2027-03-31입니다. 남은 원금은 {{principal_remaining}}입니다."
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: text)

    reply = agent.handle(_req("C002"))

    assert reply.text == text


def test_non_extendable_contradiction_falls_back(monkeypatch):
    # 슬롯을 안 쓰고 모델이 직접 "가능합니다"를 써서 C003(extendable=False)과 모순됨 — LN-004 d 이중 검증
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: "연장이 가능합니다.")

    reply = agent.handle(_req("C003"))

    assert reply.text == fallback_text(get_loans("C003")[0])


@pytest.mark.parametrize(
    ("customer_id", "expected"),
    [
        ("C002", "연장 가능 대상으로 조회됩니다."),
        ("C003", "현재 연장 가능으로 조회되지 않습니다."),
    ],
)
@pytest.mark.parametrize(
    "mock_text",
    [
        "{{extendable_status}} 안내드립니다.",  # 슬롯을 씀
        "연장이 가능합니다.",  # 슬롯 없이 직접 씀(검증 실패 가능)
        "만기일은 알 수 없습니다.",  # 연장 관련 언급 없음
    ],
)
def test_extendable_status_slot_always_matches_mock_regardless_of_model_output(
    monkeypatch, customer_id, expected, mock_text
):
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: mock_text)

    reply = agent.handle(_req(customer_id))

    assert reply.slots["extendable_status"] == expected


def test_extendable_status_slot_is_allowed_and_passes_through(monkeypatch):
    text = "{{extendable_status}} 참고해 주세요."
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: text)

    reply = agent.handle(_req("C002"))

    assert reply.text == text


def test_history_included_in_order(monkeypatch):
    captured = {}

    def fake_generate(model, messages, **options):
        captured["messages"] = messages
        return "만기일은 2027-03-31입니다."

    monkeypatch.setattr("app.llm.generate", fake_generate)
    history = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "무엇을 도와드릴까요?"},
    ]

    agent.handle(_req("C002", "만기일 알려주세요", history=history))

    assert captured["messages"][1:3] == history


def test_mask_map_not_sent_to_model(monkeypatch):
    captured = {}

    def fake_generate(model, messages, **options):
        captured["messages"] = messages
        return "만기일은 2027-03-31입니다."

    monkeypatch.setattr("app.llm.generate", fake_generate)

    agent.handle(_req("C002"))

    dumped = json.dumps(captured["messages"], ensure_ascii=False)
    assert "110-1234-5678" not in dumped
