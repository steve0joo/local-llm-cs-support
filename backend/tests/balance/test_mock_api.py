import json
import re
from pathlib import Path

from app.agents.balance.mock_api import get_accounts, get_transactions

_DATA_PATH = Path(__file__).resolve().parents[2] / "app" / "agents" / "balance" / "mock_data.json"
_RAW_DATA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

_ACCOUNT_IDS = ["A001", "A002", "A003", "A004"]


def test_get_accounts_c001():
    assert get_accounts("C001") == [
        {
            "account_id": "A001",
            "account_no": "110-1234-5678",
            "alias": "입출금",
            "balance": 1234567,
        }
    ]


def test_get_accounts_c002_order():
    result = get_accounts("C002")
    assert [a["account_id"] for a in result] == ["A002", "A003"]


def test_get_accounts_c003():
    result = get_accounts("C003")
    assert [a["account_id"] for a in result] == ["A004"]


def test_get_accounts_unknown_customer_returns_empty():
    assert get_accounts("C999") == []


def test_get_accounts_dict_keys_exact():
    for customer_id in ("C001", "C002", "C003"):
        for account in get_accounts(customer_id):
            assert set(account.keys()) == {"account_id", "account_no", "alias", "balance"}
            assert isinstance(account["account_id"], str)
            assert isinstance(account["account_no"], str)
            assert isinstance(account["alias"], str)
            assert isinstance(account["balance"], int)


def test_get_accounts_returns_copy_not_shared_state():
    first = get_accounts("C001")
    first[0]["balance"] = -1
    second = get_accounts("C001")
    assert second[0]["balance"] == 1234567


def test_mock_data_has_at_least_five_transactions_per_account():
    for account_id in _ACCOUNT_IDS:
        assert len(_RAW_DATA["transactions"][account_id]) >= 5


def test_get_transactions_default_limit_five():
    for account_id in _ACCOUNT_IDS:
        assert len(get_transactions(account_id)) == 5


def test_get_transactions_limit_three():
    for account_id in _ACCOUNT_IDS:
        assert len(get_transactions(account_id, limit=3)) == 3


def test_get_transactions_unknown_account_returns_empty():
    assert get_transactions("A999") == []


def test_get_transactions_dict_keys_exact():
    for account_id in _ACCOUNT_IDS:
        for txn in get_transactions(account_id):
            assert set(txn.keys()) == {"date", "description", "amount", "balance_after"}
            assert isinstance(txn["date"], str)
            assert isinstance(txn["description"], str)
            assert isinstance(txn["amount"], int)
            assert isinstance(txn["balance_after"], int)


def test_get_transactions_dates_non_increasing():
    for account_id in _ACCOUNT_IDS:
        txns = get_transactions(account_id, limit=len(_RAW_DATA["transactions"][account_id]))
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates, reverse=True)


def test_get_transactions_returns_copy_not_shared_state():
    first = get_transactions("A001")
    first[0]["amount"] = 0
    second = get_transactions("A001")
    assert second[0]["amount"] != 0


_ACCOUNTS_BY_ID = {
    "A001": 1234567,
    "A002": 850000,
    "A003": 2400000,
    "A004": 320000,
}


def test_balance_chain_arr0_matches_account_balance():
    for account_id, balance in _ACCOUNTS_BY_ID.items():
        txns = get_transactions(account_id)
        assert txns[0]["balance_after"] == balance


def test_balance_chain_formula_holds():
    for account_id in _ACCOUNT_IDS:
        all_txns = get_transactions(account_id, limit=len(_RAW_DATA["transactions"][account_id]))
        for i in range(len(all_txns) - 1):
            assert all_txns[i]["balance_after"] == all_txns[i + 1]["balance_after"] + all_txns[i]["amount"]


def test_transaction_amount_nonzero_and_no_digits_in_description():
    for account_id in _ACCOUNT_IDS:
        for txn in get_transactions(account_id, limit=len(_RAW_DATA["transactions"][account_id])):
            assert txn["amount"] != 0
            assert not re.search(r"\d", txn["description"])
