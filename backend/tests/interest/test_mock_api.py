import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.interest.mock_api import get_interest, mock_router

FIELDS = {
    "loan_id", "product_type", "repayment_method", "interest_type", "payment_method",
    "next_due_date", "interest_due", "overdue_amount", "overdue_days",
}


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
    for customer_id in ("C001", "C002", "C003", "C004", "C005", "C006", "C007"):
        for item in get_interest(customer_id):
            assert set(item) == FIELDS
            assert isinstance(item["interest_due"], int)
            assert isinstance(item["overdue_amount"], int)
            assert all(isinstance(item[k], str) for k in ("repayment_method", "interest_type", "payment_method"))


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
            "repayment_method": "만기일시",
            "interest_type": "변동",
            "payment_method": "자동이체",
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
            "repayment_method": "원리금균등",
            "interest_type": "고정",
            "payment_method": "가상계좌 입금",
            "next_due_date": "2026-10-25",
            "interest_due": 312500,
            "overdue_amount": 625000,
            "overdue_days": 12,
        }
    ]


NEW_CUSTOMERS = {
    # docs/agent-interest/ARCHITECTURE.md "mock 데이터" 표 — 계약 6 확장 제안(팀 합의 대기)
    "C004": {"loan_id": "L003", "product_type": "신용대출", "repayment_method": "원리금균등", "interest_type": "변동",
             "payment_method": "자동이체", "next_due_date": "2026-10-20", "interest_due": 41500,
             "overdue_amount": 890000, "overdue_days": 65},
    "C005": {"loan_id": "L004", "product_type": "전세자금대출", "repayment_method": "원금균등", "interest_type": "고정",
             "payment_method": "가상계좌 입금", "next_due_date": "2026-10-10", "interest_due": 176000,
             "overdue_amount": 0, "overdue_days": 0},
    "C006": {"loan_id": "L005", "product_type": "주택담보대출", "repayment_method": "원리금균등", "interest_type": "고정",
             "payment_method": "자동이체", "next_due_date": "2026-10-26", "interest_due": 405000,
             "overdue_amount": 548000, "overdue_days": 2},
    "C007": {"loan_id": "L006", "product_type": "신용대출", "repayment_method": "만기일시", "interest_type": "변동",
             "payment_method": "자동이체", "next_due_date": "2026-09-30", "interest_due": 27500,
             "overdue_amount": 0, "overdue_days": 0},
}


@pytest.mark.parametrize("customer_id", sorted(NEW_CUSTOMERS))
def test_new_customers_match_table(customer_id):
    assert get_interest(customer_id) == [NEW_CUSTOMERS[customer_id]]


def test_scenarios_cover_variety():
    # 데모 값을 외웠는지 드러나도록 연체 일수·납부·상환·금리 방식이 고루 나와야 한다.
    items = [i for c in ("C002", "C003", "C004", "C005", "C006", "C007") for i in get_interest(c)]
    assert {i["overdue_days"] for i in items} >= {0, 2, 12, 65}
    assert {i["payment_method"] for i in items} == {"자동이체", "가상계좌 입금"}
    assert {i["repayment_method"] for i in items} == {"원리금균등", "원금균등", "만기일시"}
    assert {i["interest_type"] for i in items} == {"고정", "변동"}
    assert len({i["loan_id"] for i in items}) == len(items)  # 대출 ID 중복 없음
