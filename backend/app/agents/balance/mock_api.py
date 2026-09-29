import copy
import json
from pathlib import Path

from fastapi import APIRouter

_DATA: dict = json.loads(
    (Path(__file__).with_name("mock_data.json")).read_text(encoding="utf-8")
)

mock_router = APIRouter()


def get_accounts(customer_id: str) -> list[dict]:
    return copy.deepcopy(_DATA["accounts"].get(customer_id, []))


def get_transactions(account_id: str, limit: int = 5) -> list[dict]:
    return copy.deepcopy(_DATA["transactions"].get(account_id, [])[:limit])


@mock_router.get("/mock/customers/{customer_id}/accounts")
def read_accounts(customer_id: str) -> list[dict]:
    return get_accounts(customer_id)


@mock_router.get("/mock/accounts/{account_id}/transactions")
def read_transactions(account_id: str, limit: int = 5) -> list[dict]:
    return get_transactions(account_id, limit)
