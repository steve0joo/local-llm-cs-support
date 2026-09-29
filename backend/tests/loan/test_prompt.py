import copy
import json
import re

import pytest

from app.agents.loan.mock_api import get_loans
from app.agents.loan.prompt import (
    NO_LOAN_TEXT,
    SYSTEM_PROMPT,
    build_messages,
    build_slots,
    fallback_text,
)
from app.agents.loan.validate import is_valid_output


@pytest.fixture()
def extendable_loan() -> dict:
    return get_loans("C002")[0]


@pytest.fixture()
def non_extendable_loan() -> dict:
    return get_loans("C003")[0]


def test_no_loan_text():
    assert NO_LOAN_TEXT == "고객님 명의로 조회되는 대출이 없습니다."


def test_system_prompt_rules():
    assert "상담원" in SYSTEM_PROMPT
    assert "{{principal_remaining}}" in SYSTEM_PROMPT
    assert "존댓말" in SYSTEM_PROMPT
    # 숫자 예시(금리·금액 등)를 넣으면 모델이 그대로 답할 수 있다
    assert not re.search(r"\d", SYSTEM_PROMPT)
    assert "%" not in SYSTEM_PROMPT
    # 연장 가능 여부는 직접 쓰지 말고 슬롯으로 표현하라는 지시가 있어야 한다(2026-09-29)
    assert "{{extendable_status}}" in SYSTEM_PROMPT


def test_build_messages_structure(extendable_loan):
    history = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "무엇을 도와드릴까요?"},
    ]
    messages = build_messages(history, "제 대출 만기가 언제예요?", extendable_loan)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1:3] == history
    last = messages[-1]
    assert last["role"] == "user"
    assert "제 대출 만기가 언제예요?" in last["content"]
    assert "종류=신용대출" in last["content"]
    assert "만기일=2027-03-31" in last["content"]
    assert "연장 가능=예" in last["content"]
    assert "{{loan_label}}, {{principal_remaining}}, {{extendable_status}}" in last["content"]
    assert len(messages) == 4


def test_build_messages_non_extendable(non_extendable_loan):
    last = build_messages([], "연장되나요?", non_extendable_loan)[-1]["content"]
    assert "종류=주택담보대출" in last
    assert "연장 가능=아니오(사유는 알 수 없음)" in last


@pytest.mark.parametrize("customer_id", ["C002", "C003"])
def test_principal_never_in_prompt(customer_id):
    loan = get_loans(customer_id)[0]
    amount = loan["principal_remaining"]
    dumped = json.dumps(build_messages([], "남은 원금이 얼마예요?", loan), ensure_ascii=False)
    assert str(amount) not in dumped
    assert f"{amount:,}" not in dumped


def test_build_messages_does_not_mutate_inputs(extendable_loan):
    history = [{"role": "user", "content": "안녕하세요"}]
    history_before = copy.deepcopy(history)
    loan_before = copy.deepcopy(extendable_loan)

    messages = build_messages(history, "만기일 알려주세요", extendable_loan)
    messages[1]["content"] = "변경"  # 반환값을 바꿔도 입력 history는 그대로여야 한다

    assert history == history_before
    assert extendable_loan == loan_before


def test_build_slots():
    assert build_slots(get_loans("C002")[0]) == {
        "loan_label": "신용대출",
        "principal_remaining": "12,000,000원",
        "extendable_status": "연장 가능 대상으로 조회됩니다.",
    }
    assert build_slots(get_loans("C003")[0]) == {
        "loan_label": "주택담보대출",
        "principal_remaining": "85,000,000원",
        "extendable_status": "현재 연장 가능으로 조회되지 않습니다.",
    }


def test_fallback_text_extendable(extendable_loan):
    text = fallback_text(extendable_loan)
    assert text == (
        "{{loan_label}}의 만기일은 2027-03-31이고, 남은 원금은 {{principal_remaining}}입니다."
        " {{extendable_status}}"
        " 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요."
    )


def test_fallback_text_non_extendable(non_extendable_loan):
    text = fallback_text(non_extendable_loan)
    assert text == (
        "{{loan_label}}의 만기일은 2035-06-30이고, 남은 원금은 {{principal_remaining}}입니다."
        " {{extendable_status}}"
        " 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요."
    )


@pytest.mark.parametrize("customer_id", ["C002", "C003"])
def test_fallback_passes_own_validation(customer_id):
    # 기본 문장이 자기 검증에 걸리면 대체해도 계속 대체되는 버그가 된다
    loan = get_loans(customer_id)[0]
    text = fallback_text(loan)
    assert "{{loan_label}}" in text
    assert "{{principal_remaining}}" in text
    assert "{{extendable_status}}" in text
    assert is_valid_output(
        text, maturity_date=loan["maturity_date"], extendable=loan["extendable"]
    )
