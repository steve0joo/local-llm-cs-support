"""InterestAgent.handle() — docs/agent-interest/ARCHITECTURE.md handle() 흐름·테스트 절.

팀원C의 app.agents.base(계약 3)와 app.llm(계약 5)이 main에 오기 전에는 건너뛴다.
"""

import json

import pytest

pytest.importorskip("app.agents.base", reason="계약 3 스텁(app/agents/base.py)이 main에 오기 전")
pytest.importorskip("app.llm", reason="계약 5 app.llm이 main에 오기 전")

from app.agents.base import AgentReply, AgentRequest  # noqa: E402
from app.agents.interest.agent import MODEL, NO_LOAN_TEXT, InterestAgent  # noqa: E402

FALLBACK_C003 = (
    "{{loan_label}}의 다음 납부일은 2026-10-25이고, 납부 예정 이자는 {{interest_due}}입니다."
    " 현재 12일 연체 중이며 연체 금액은 {{overdue_amount}}입니다."
    " 고객님 대출의 납부 방법은 가상계좌 입금이니 가능한 빨리 납부해 주시기 바랍니다. 자세한 사항은 상담원에게 확인해 주세요."
)


def request(customer_id, text, history=()):
    return AgentRequest(session_id="s1", customer_id=customer_id, masked_text=text, mask_map={}, history=list(history))


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def install(answer):
        def generate(model, messages, **options):
            calls.append({"model": model, "messages": messages})
            return answer

        monkeypatch.setattr("app.llm.generate", generate)
        return calls

    return install


def test_agent_name():
    assert InterestAgent().name == "interest"


def test_no_loan_does_not_call_model(fake_llm):
    calls = fake_llm("호출되면 안 된다")
    reply = InterestAgent().handle(request("C001", "이자 얼마예요?"))
    assert reply == AgentReply(text=NO_LOAN_TEXT, slots={}, options=[])
    assert calls == []


def test_valid_answer_passes_with_slots(fake_llm):
    calls = fake_llm("다음 납부일은 2026-10-15이고, 납부하실 이자는 {{interest_due}}입니다.")
    reply = InterestAgent().handle(request("C002", "이번 달 이자 얼마예요?"))

    assert reply.text == "다음 납부일은 2026-10-15이고, 납부하실 이자는 {{interest_due}}입니다."
    # C002는 자동이체라 자동이체 계좌(A002) 잔액 슬롯도 붙는다(balance_source.enrich)
    assert reply.slots == {"loan_label": "신용대출", "interest_due": "58,000원", "debit_balance": "850,000원"}
    assert reply.options == []
    [call] = calls
    assert call["model"] == MODEL == "cs-interest"


def test_prompt_never_contains_amounts(fake_llm):
    # CLAUDE.md CRITICAL: mock 금액은 프롬프트에 넣지 않는다.
    calls = fake_llm("연체 금액은 {{overdue_amount}}입니다. 현재 12일 연체 중입니다.")
    InterestAgent().handle(request("C003", "연체된 거 있어요?"))
    text = json.dumps(calls[0]["messages"], ensure_ascii=False)
    for amount in ("312500", "312,500", "625000", "625,000"):
        assert amount not in text


def test_history_is_passed_through(fake_llm):
    history = [{"role": "user", "content": "이자 얼마예요?"}, {"role": "assistant", "content": "{{interest_due}}입니다."}]
    calls = fake_llm("다음 납부일은 2026-10-15입니다.")
    InterestAgent().handle(request("C002", "언제까지 내요?", history))
    assert calls[0]["messages"][1:3] == history


@pytest.mark.parametrize(
    "answer",
    ["적용 금리는 4.5%입니다.", "이자는 312,500원입니다.", "잔액은 {{balance}}입니다.", "말씀하신 [금액_1]은 맞습니다.", ""],
)
def test_invalid_answer_falls_back(fake_llm, answer):
    fake_llm(answer)
    reply = InterestAgent().handle(request("C003", "이자 얼마예요?"))
    assert reply.text == FALLBACK_C003


def test_overdue_question_without_amount_falls_back(fake_llm):
    fake_llm("현재 연체 중이니 빨리 납부해 주세요.")
    reply = InterestAgent().handle(request("C003", "연체된 거 있어요?"))
    assert reply.text == FALLBACK_C003
    assert reply.slots["overdue_amount"] == "625,000원"


def test_rate_question_with_staff_guidance_passes(fake_llm):
    # 연체 고객의 금리 질문에 상담원 안내만 한 답은 대체하지 않는다(validate.required_slots).
    fake_llm("적용 금리 수치는 상담원에게 확인해 주세요.")
    reply = InterestAgent().handle(request("C003", "대출 금리가 몇 %예요?"))
    assert reply.text == "적용 금리 수치는 상담원에게 확인해 주세요."



def test_model_failure_falls_back(monkeypatch):
    # Ollama가 꺼져 있거나 시간 초과여도 고객에게는 조회 사실만 담은 기본 문장을 돌려준다.
    def generate(model, messages, **options):
        raise TimeoutError("ollama")

    monkeypatch.setattr("app.llm.generate", generate)
    reply = InterestAgent().handle(request("C003", "연체된 거 있어요?"))
    assert reply.text == FALLBACK_C003
    assert reply.slots["overdue_amount"] == "625,000원"
