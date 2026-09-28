from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.interest.mock_api import get_interest, mock_router

FIELDS = {"loan_id", "product_type", "next_due_date", "interest_due", "overdue_amount", "overdue_days"}


def test_customer_without_loan_has_no_items():
    assert get_interest("C001") == []


def test_unknown_customer_has_no_items():
    assert get_interest("C999") == []


def test_normal_loan_has_no_overdue():
    [item] = get_interest("C002")
    assert item["loan_id"] == "L001"
    assert item["product_type"] == "신용대출"
    assert item["overdue_days"] == 0
    assert item["overdue_amount"] == 0


def test_overdue_loan():
    [item] = get_interest("C003")
    assert item["loan_id"] == "L002"
    assert item["product_type"] == "주택담보대출"
    assert item["overdue_days"] > 0
    assert item["overdue_amount"] > 0


def test_items_have_contract_fields_and_no_rate():
    # INT-002: 금리·이율 필드를 두지 않는다. 금액은 정수(원).
    for customer_id in ("C001", "C002", "C003"):
        for item in get_interest(customer_id):
            assert set(item) == FIELDS
            assert isinstance(item["interest_due"], int)
            assert isinstance(item["overdue_amount"], int)


def test_returned_items_are_copies():
    get_interest("C002")[0]["interest_due"] = 0
    assert get_interest("C002")[0]["interest_due"] != 0


def test_mock_route():
    app = FastAPI()
    app.include_router(mock_router)
    client = TestClient(app)

    res = client.get("/mock/customers/C003/interest")
    assert res.status_code == 200
    assert res.json() == get_interest("C003")

    assert client.get("/mock/customers/C001/interest").json() == []


def test_matches_mock_data_table():
    # docs/agent-interest/ARCHITECTURE.md "mock 데이터" 표
    assert get_interest("C002") == [
        {
            "loan_id": "L001",
            "product_type": "신용대출",
            "next_due_date": "2026-10-15",
            "interest_due": 58000,
            "overdue_amount": 0,
            "overdue_days": 0,
        }
    ]
    assert get_interest("C003") == [
        {
            "loan_id": "L002",
            "product_type": "주택담보대출",
            "next_due_date": "2026-10-25",
            "interest_due": 312500,
            "overdue_amount": 625000,
            "overdue_days": 12,
        }
    ]
