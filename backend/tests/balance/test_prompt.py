import copy
import json
import re

import pytest

from app.agents.balance.mock_api import get_accounts, get_transactions
from app.agents.balance.prompt import (
    SLOT_NAMES,
    SYSTEM_PROMPT,
    build_messages,
    build_slots,
    fallback_text,
)

A001 = get_accounts("C001")[0]
A002, A003 = get_accounts("C002")
A004 = get_accounts("C003")[0]
ACCOUNTS = [A001, A002, A003, A004]

EXPECTED_TRANSACTIONS_TEXT = (
    "2026-09-28 · 이체입금 · +150,000원\n"
    "2026-09-20 · 편의점 · -8,000원\n"
    "2026-09-15 · 통신요금 · -65,000원\n"
    "2026-09-10 · 관리비 · -180,000원\n"
    "2026-09-05 · 카드대금 · -450,000원"
)

_HISTORY = [
    {"role": "user", "content": "잔액 알려줘"},
    {"role": "assistant", "content": "어느 계좌를 조회할까요?"},
    {"role": "user", "content": "입출금 ****5678"},
]

# A001의 mock_data.json 원본 값(잔액·거래 금액·balance_after)을 손으로 옮겨 적었다.
FORBIDDEN_STRINGS = [
    "1234567",
    "1,234,567",
    "110-1234-5678",
    "11012345678",
    "150000",
    "150,000",
    "8000",
    "8,000",
    "65000",
    "65,000",
    "180000",
    "180,000",
    "450000",
    "450,000",
    "2600000",
    "2,600,000",
    "1084567",
    "1092567",
    "1157567",
    "1337567",
    "1787567",
]


def test_slot_names_contract():
    assert SLOT_NAMES == {
        "balance": ("account_label", "balance"),
        "transactions": ("account_label", "recent_transactions"),
        "general": (),
    }


def test_build_slots_balance():
    assert build_slots("balance", A001) == {
        "account_label": "입출금 ****5678",
        "balance": "1,234,567원",
    }


def test_build_slots_general_is_empty():
    assert build_slots("general", None) == {}


@pytest.mark.parametrize("account", ACCOUNTS)
def test_build_slots_balance_values_are_str(account):
    slots = build_slots("balance", account)
    assert all(isinstance(v, str) for v in slots.values())


@pytest.mark.parametrize("account", ACCOUNTS)
def test_build_slots_transactions_values_are_str(account):
    slots = build_slots(
        "transactions", account, get_transactions(account["account_id"])
    )
    assert all(isinstance(v, str) for v in slots.values())


def test_build_slots_transactions_recent_transactions_literal():
    slots = build_slots("transactions", A001, get_transactions("A001"))
    assert slots["recent_transactions"] == EXPECTED_TRANSACTIONS_TEXT


def test_build_slots_transactions_account_label():
    slots = build_slots("transactions", A001, get_transactions("A001"))
    assert slots["account_label"] == "입출금 ****5678"


def test_build_messages_structure():
    messages = build_messages(_HISTORY, "잔액 알려줘", "balance")
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1:-1] == _HISTORY


def test_build_messages_balance_user_content_ends_with_slot_line():
    messages = build_messages([], "잔액 알려줘", "balance")
    assert (
        messages[-1]["content"]
        == "잔액 알려줘\n사용할 수 있는 슬롯: {{account_label}}, {{balance}}"
    )


def test_build_messages_transactions_user_content_ends_with_slot_line():
    messages = build_messages([], "최근 거래내역 보여줘", "transactions")
    assert (
        messages[-1]["content"]
        == "최근 거래내역 보여줘\n사용할 수 있는 슬롯: {{account_label}}, {{recent_transactions}}"
    )


def test_build_messages_general_user_content_is_unchanged():
    messages = build_messages([], "잔액 조회는 어디서 해요?", "general")
    assert messages[-1]["content"] == "잔액 조회는 어디서 해요?"


def test_build_messages_balance_no_raw_amounts():
    messages = build_messages(_HISTORY, "잔액 알려줘", "balance")
    dumped = json.dumps(messages, ensure_ascii=False)
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in dumped


def test_build_messages_transactions_no_raw_amounts():
    messages = build_messages(_HISTORY, "최근 거래내역 보여줘", "transactions")
    dumped = json.dumps(messages, ensure_ascii=False)
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in dumped


def test_build_messages_general_no_raw_amounts():
    messages = build_messages(_HISTORY, "잔액 조회는 어디서 해요?", "general")
    dumped = json.dumps(messages, ensure_ascii=False)
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in dumped


def test_build_messages_does_not_mutate_history():
    history = copy.deepcopy(_HISTORY)
    history_before = copy.deepcopy(history)
    build_messages(history, "잔액 알려줘", "balance")
    assert history == history_before


def test_build_messages_returns_copies_not_references():
    history = [{"role": "user", "content": "잔액 알려줘"}]
    messages = build_messages(history, "잔액 알려줘", "balance")
    messages[1]["content"] = "변경됨"
    assert history[0]["content"] == "잔액 알려줘"


def test_system_prompt_has_no_digits():
    assert not re.search(r"\d", SYSTEM_PROMPT)


def test_system_prompt_has_no_percent():
    assert "%" not in SYSTEM_PROMPT


def test_system_prompt_mentions_honorifics_and_agent():
    assert "존댓말" in SYSTEM_PROMPT
    assert "상담원" in SYSTEM_PROMPT


def test_fallback_text_balance():
    assert fallback_text("balance") == "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다."


def test_fallback_text_transactions():
    assert (
        fallback_text("transactions")
        == "{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"
    )


def test_fallback_text_general():
    assert fallback_text("general") == "해당 내용은 정확한 안내를 위해 상담원에게 확인해 주세요."
