import json

import pytest

from app.agents.interest.balance_source import debit_check, enrich, get_accounts
from app.agents.interest.mock_api import get_interest

# 잔액조회(팀장) mock 데이터 표(docs/agent-balance/ARCHITECTURE.md, feat-agent-balance)와 같아야 한다.
LEADER_ACCOUNTS = {
    "C001": [{"account_id": "A001", "account_no": "110-1234-5678", "alias": "입출금", "balance": 1234567}],
    "C002": [
        {"account_id": "A002", "account_no": "110-2345-6789", "alias": "입출금", "balance": 850000},
        {"account_id": "A003", "account_no": "110-3456-7890", "alias": "생활비", "balance": 2400000},
    ],
    "C003": [{"account_id": "A004", "account_no": "110-4567-8901", "alias": "입출금", "balance": 320000}],
}


@pytest.mark.parametrize("customer_id", sorted(LEADER_ACCOUNTS))
def test_demo_accounts_match_balance_agent(customer_id):
    # 병합 후 잔액조회의 get_accounts로 바꿔도 결과가 같도록 값을 그대로 둔다.
    assert get_accounts(customer_id) == LEADER_ACCOUNTS[customer_id]


def test_unknown_customer_has_no_accounts():
    assert get_accounts("C999") == []


def test_accounts_are_copies():
    get_accounts("C002")[0]["balance"] = 0
    assert get_accounts("C002")[0]["balance"] == 850000


@pytest.mark.parametrize(
    ("balance", "overdue_days", "status"),
    [
        (12300, 65, "연체 금액보다 적음"),
        (1000000, 65, "연체 금액 이상"),
        (10000, 0, "납부 예정 이자보다 적음"),
        (850000, 0, "납부 예정 이자 이상"),
    ],
)
def test_debit_check_compares_in_code(balance, overdue_days, status):
    item = {"payment_method": "자동이체", "overdue_days": overdue_days, "overdue_amount": 890000, "interest_due": 58000}
    assert debit_check(item, balance) == status


def test_debit_check_not_applicable():
    assert debit_check({"payment_method": "가상계좌 입금", "overdue_days": 12, "overdue_amount": 1, "interest_due": 1}, 5) is None
    assert debit_check({"payment_method": "자동이체", "overdue_days": 0, "overdue_amount": 0, "interest_due": 1}, None) is None


@pytest.mark.parametrize(
    ("customer_id", "status", "balance"),
    [
        ("C002", "납부 예정 이자 이상", 850000),
        ("C004", "연체 금액보다 적음", 12300),
        ("C006", "연체 금액보다 적음", 150000),
        ("C007", "납부 예정 이자 이상", 500000),
    ],
)
def test_enrich_autodebit_customers(customer_id, status, balance):
    item = enrich(get_interest(customer_id)[0], customer_id)
    assert item["debit_status"] == status and item["debit_balance"] == balance


@pytest.mark.parametrize("customer_id", ["C003", "C005"])
def test_enrich_virtual_account_customers_unchanged(customer_id):
    original = get_interest(customer_id)[0]
    assert enrich(original, customer_id) == original


def test_enrich_does_not_mutate_input():
    original = get_interest("C004")[0]
    snapshot = json.dumps(original, sort_keys=True)
    enrich(original, "C004")
    assert json.dumps(original, sort_keys=True) == snapshot
