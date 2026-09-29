from app.agents.interest.prompt import (
    SYSTEM_PROMPT,
    build_messages,
    build_slots,
    fallback_text,
    format_won,
    info_line,
    slot_line,
)

NORMAL = {
    "loan_id": "L001",
    "product_type": "신용대출",
    "repayment_method": "만기일시",
    "interest_type": "변동",
    "payment_method": "자동이체",
    "next_due_date": "2026-10-25",
    "interest_due": 48000,
    "overdue_amount": 0,
    "overdue_days": 0,
}
OVERDUE = {
    "loan_id": "L002",
    "product_type": "주택담보대출",
    "repayment_method": "원리금균등",
    "interest_type": "고정",
    "payment_method": "가상계좌 입금",
    "next_due_date": "2026-10-25",
    "interest_due": 312500,
    "overdue_amount": 625000,
    "overdue_days": 12,
}


def test_format_won():
    assert format_won(312500) == "312,500원"
    assert format_won(0) == "0원"


def test_slots_without_overdue():
    assert build_slots(NORMAL) == {"loan_label": "신용대출", "interest_due": "48,000원"}


def test_slots_with_overdue():
    assert build_slots(OVERDUE) == {
        "loan_label": "주택담보대출",
        "interest_due": "312,500원",
        "overdue_amount": "625,000원",
    }


def test_info_line_has_no_amount():
    # 금액은 슬롯으로만 흐른다. 날짜·일수·종류만 프롬프트에 넣는다.
    line = info_line(OVERDUE)
    assert line == "이자 정보: 종류=주택담보대출, 상환 방식=원리금균등, 금리 방식=고정, 납부 방법=가상계좌 입금, 다음 납부일=2026-10-25, 연체 여부=연체 중, 연체 일수=12"
    assert "312" not in line and "625" not in line


def test_info_line_states_no_overdue():
    assert info_line(NORMAL) == "이자 정보: 종류=신용대출, 상환 방식=만기일시, 금리 방식=변동, 납부 방법=자동이체, 다음 납부일=2026-10-25, 연체 여부=연체 없음"


def test_slot_line():
    assert slot_line(["loan_label", "interest_due"]) == "사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}"


def test_build_messages_order_and_content():
    history = [
        {"role": "user", "content": "이자 얼마예요?"},
        {"role": "assistant", "content": "납부 예정 이자는 {{interest_due}}입니다."},
    ]
    messages = build_messages("연체된 거 있어요?", history, OVERDUE)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1:3] == history
    last = messages[-1]
    assert last["role"] == "user"
    assert last["content"] == (
        "연체된 거 있어요?\n"
        "이자 정보: 종류=주택담보대출, 상환 방식=원리금균등, 금리 방식=고정, 납부 방법=가상계좌 입금, 다음 납부일=2026-10-25, 연체 여부=연체 중, 연체 일수=12\n"
        "사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}, {{overdue_amount}}"
    )


def test_build_messages_does_not_leak_amounts():
    messages = build_messages("이자 얼마예요?", [], OVERDUE)
    text = "".join(m["content"] for m in messages)
    assert "312,500" not in text and "625,000" not in text


def test_fallback_without_overdue():
    assert fallback_text(NORMAL) == (
        "{{loan_label}}의 다음 납부일은 2026-10-25이고, 납부 예정 이자는 {{interest_due}}입니다."
        " 자세한 사항은 상담원에게 확인해 주세요."
    )


def test_fallback_with_overdue():
    assert fallback_text(OVERDUE) == (
        "{{loan_label}}의 다음 납부일은 2026-10-25이고, 납부 예정 이자는 {{interest_due}}입니다."
        " 현재 12일 연체 중이며 연체 금액은 {{overdue_amount}}입니다."
        " 고객님 대출의 납부 방법은 가상계좌 입금이니 가능한 빨리 납부해 주시기 바랍니다."
        " 자세한 사항은 상담원에게 확인해 주세요."
    )


# --- 자동이체 계좌 잔액 비교(balance_source.enrich가 붙인 값) ------------------------------

DEBIT = {**OVERDUE, "payment_method": "자동이체", "debit_status": "연체 금액보다 적음", "debit_balance": 12300}


def test_info_line_includes_debit_status():
    assert info_line(DEBIT).endswith(", 연체 일수=12, 자동이체 계좌 잔액=연체 금액보다 적음")


def test_debit_balance_is_slot_not_prompt():
    # 잔액 금액은 슬롯으로만 흐른다. 모델에는 비교 결과 문장만 들어간다.
    assert build_slots(DEBIT)["debit_balance"] == "12,300원"
    text = "".join(m["content"] for m in build_messages("왜 연체예요?", [], DEBIT))
    assert "12300" not in text and "12,300" not in text
    assert "{{debit_balance}}" in text  # 사용할 수 있는 슬롯 줄에는 이름만


def test_no_debit_fields_no_debit_line():
    assert "자동이체 계좌 잔액" not in info_line(OVERDUE)
    assert "debit_balance" not in build_slots(OVERDUE)
