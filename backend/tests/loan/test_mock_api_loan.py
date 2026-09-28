import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.loan.mock_api import get_loans, mock_router

APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(mock_router)
    return TestClient(app)


def test_c002_has_one_credit_loan(client):
    res = client.get("/mock/customers/C002/loans")
    assert res.status_code == 200
    assert res.json() == [
        {
            "loan_id": "L001",
            "product_type": "신용대출",
            "principal_remaining": 12000000,
            "maturity_date": "2027-03-31",
            "extendable": True,
        }
    ]


def test_c003_has_non_extendable_mortgage(client):
    res = client.get("/mock/customers/C003/loans")
    assert res.status_code == 200
    assert res.json() == [
        {
            "loan_id": "L002",
            "product_type": "주택담보대출",
            "principal_remaining": 85000000,
            "maturity_date": "2035-06-30",
            "extendable": False,
        }
    ]


@pytest.mark.parametrize("customer_id", ["C001", "C999"])
def test_no_loans_returns_empty_list_not_404(client, customer_id):
    res = client.get(f"/mock/customers/{customer_id}/loans")
    assert res.status_code == 200
    assert res.json() == []


def test_no_rate_or_reason_fields(client):
    forbidden = ("rate", "interest", "금리", "이율", "reason", "사유")
    for customer_id in ("C001", "C002", "C003"):
        for loan in client.get(f"/mock/customers/{customer_id}/loans").json():
            assert not [k for k in loan if any(f in k.lower() for f in forbidden)]


def test_field_types(client):
    for customer_id in ("C002", "C003"):
        for loan in client.get(f"/mock/customers/{customer_id}/loans").json():
            assert isinstance(loan["principal_remaining"], int)
            assert isinstance(loan["extendable"], bool)
            assert len(loan["maturity_date"]) == 10  # YYYY-MM-DD


def test_get_loans_returns_copy(client):
    loans = get_loans("C002")
    loans[0]["principal_remaining"] = 1
    loans.append({"loan_id": "X"})
    assert get_loans("C002")[0]["principal_remaining"] == 12000000
    assert len(get_loans("C002")) == 1


def test_get_loans_unknown_customer():
    assert get_loans("C999") == []


def test_matches_interest_mock_when_present():
    interest_path = APP_DIR / "agents" / "interest" / "mock_data.json"
    if not interest_path.exists():
        pytest.skip("interest mock_data.json 아직 없음")
    interest = json.loads(interest_path.read_text(encoding="utf-8"))
    loan_types = {
        loan["loan_id"]: loan["product_type"]
        for loans in (get_loans(c) for c in ("C001", "C002", "C003"))
        for loan in loans
    }
    items = interest.values() if isinstance(interest, dict) else [interest]
    for entries in items:
        for entry in entries if isinstance(entries, list) else []:
            if entry.get("loan_id") in loan_types:
                assert entry["product_type"] == loan_types[entry["loan_id"]]
