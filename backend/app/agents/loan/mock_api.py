import copy
import json
from pathlib import Path

from fastapi import APIRouter

_DATA: dict[str, list[dict]] = json.loads(
    (Path(__file__).with_name("mock_data.json")).read_text(encoding="utf-8")
)

mock_router = APIRouter()


def get_loans(customer_id: str) -> list[dict]:
    return copy.deepcopy(_DATA.get(customer_id, []))


@mock_router.get("/mock/customers/{customer_id}/loans")
def read_loans(customer_id: str) -> list[dict]:
    return get_loans(customer_id)
