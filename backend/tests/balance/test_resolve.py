import copy

from app.agents.balance.mock_api import get_accounts
from app.agents.balance.resolve import account_label, choose_account, find_clicked

A001 = get_accounts("C001")[0]
A002, A003 = get_accounts("C002")

_HISTORY = [
    {"role": "user", "content": "최근 거래내역 보여줘"},
    {"role": "assistant", "content": "어느 계좌를 조회할까요?"},
]


def test_account_label():
    assert account_label(A001) == "입출금 ****5678"


def test_choose_account_single_account():
    assert choose_account(get_accounts("C001"), {}) == {"account": A001}


def test_choose_account_multiple_accounts_asks():
    assert choose_account(get_accounts("C002"), {}) == {
        "text": "어느 계좌를 조회할까요?",
        "options": [
            {"label": "입출금 ****6789", "choice": "balance"},
            {"label": "생활비 ****7890", "choice": "balance"},
        ],
    }


def test_choose_account_mask_map_match_with_hyphens():
    assert choose_account(get_accounts("C002"), {"[계좌번호_1]": "110-3456-7890"}) == {"account": A003}


def test_choose_account_mask_map_match_without_hyphens():
    assert choose_account(get_accounts("C002"), {"[계좌번호_1]": "11034567890"}) == {"account": A003}


def test_choose_account_not_own_account():
    assert choose_account(get_accounts("C001"), {"[계좌번호_1]": "110-9999-0000"}) == {
        "text": "입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?",
        "options": [{"label": "입출금 ****5678", "choice": "balance"}],
    }


def test_choose_account_no_accounts():
    assert choose_account([], {}) == {"text": "고객님 명의로 조회되는 계좌가 없습니다.", "options": []}


def test_choose_account_ignores_non_account_tokens():
    mask_map = {"[전화번호_1]": "010-3456-7890", "[금액_1]": "11034567890"}
    assert choose_account(get_accounts("C002"), mask_map) == {
        "text": "어느 계좌를 조회할까요?",
        "options": [
            {"label": "입출금 ****6789", "choice": "balance"},
            {"label": "생활비 ****7890", "choice": "balance"},
        ],
    }
    assert choose_account(get_accounts("C001"), mask_map) == {"account": A001}


def test_choose_account_smaller_token_number_first():
    mask_map = {"[계좌번호_2]": "110-2345-6789", "[계좌번호_1]": "110-3456-7890"}
    assert choose_account(get_accounts("C002"), mask_map) == {"account": A003}


def test_choose_account_token_number_compared_numerically():
    mask_map = {"[계좌번호_10]": "110-2345-6789", "[계좌번호_9]": "110-3456-7890"}
    assert choose_account(get_accounts("C002"), mask_map) == {"account": A003}


def test_choose_account_later_token_matches():
    mask_map = {"[계좌번호_1]": "110-9999-0000", "[계좌번호_2]": "110-2345-6789"}
    assert choose_account(get_accounts("C002"), mask_map) == {"account": A002}


def test_choose_account_does_not_mutate_inputs():
    accounts = get_accounts("C002")
    mask_map = {"[계좌번호_1]": "110-9999-0000"}
    accounts_before = copy.deepcopy(accounts)
    mask_map_before = dict(mask_map)
    choose_account(accounts, mask_map)
    assert accounts == accounts_before
    assert mask_map == mask_map_before


def test_find_clicked_label_click_turn():
    assert find_clicked("생활비 ****7890", _HISTORY, get_accounts("C002")) == {
        "question": "최근 거래내역 보여줘",
        "account": A003,
    }


def test_find_clicked_uses_last_user_message():
    history = [
        {"role": "user", "content": "잔액 알려줘"},
        {"role": "assistant", "content": "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다."},
    ] + _HISTORY
    assert find_clicked("생활비 ****7890", history, get_accounts("C002")) == {
        "question": "최근 거래내역 보여줘",
        "account": A003,
    }


def test_find_clicked_empty_history_returns_none():
    assert find_clicked("생활비 ****7890", [], get_accounts("C002")) is None


def test_find_clicked_history_without_user_message_returns_none():
    history = [{"role": "assistant", "content": "어느 계좌를 조회할까요?"}]
    assert find_clicked("생활비 ****7890", history, get_accounts("C002")) is None


def test_find_clicked_not_a_label_returns_none():
    assert find_clicked("잔액 알려줘", _HISTORY, get_accounts("C002")) is None


def test_find_clicked_does_not_mutate_inputs():
    history = copy.deepcopy(_HISTORY)
    accounts = get_accounts("C002")
    find_clicked("생활비 ****7890", history, accounts)
    assert history == _HISTORY
    assert accounts == get_accounts("C002")
