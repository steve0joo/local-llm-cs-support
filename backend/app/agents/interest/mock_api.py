import copy
import json
from pathlib import Path

from fastapi import APIRouter

_DATA = json.loads((Path(__file__).parent / "mock_data.json").read_text(encoding="utf-8"))

mock_router = APIRouter()


def get_interest(customer_id: str) -> list[dict]:
    """고객의 대출별 이자·연체 내역. 금액은 정수(원), 금리 필드는 없다(INT-002)."""
    return copy.deepcopy(_DATA.get(customer_id, []))


@mock_router.get("/mock/customers/{customer_id}/interest")
def read_interest(customer_id: str) -> list[dict]:
    return get_interest(customer_id)
