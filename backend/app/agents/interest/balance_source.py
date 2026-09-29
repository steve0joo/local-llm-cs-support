"""자동이체 계좌 잔액 조회와 비교 (연체 원인 설명용).

잔액은 잔액조회 에이전트(팀장) 영역의 데이터다. main 병합 전에는 같은 형식을 본뜬 사본(balance_mock.json)을 읽고,
병합 후에는 get_accounts만 잔액조회의 조회 함수로 바꾼다:

    from app.agents.balance.mock_api import get_accounts

비교는 코드가 하고 모델에는 결과 문장만 준다. 잔액 금액은 슬롯({{debit_balance}})으로만 흐른다(CLAUDE.md: mock 금액은 프롬프트 금지).
"""

import copy
import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "balance_mock.json").read_text(encoding="utf-8"))


def get_accounts(customer_id: str) -> list[dict]:
    """잔액조회 mock의 get_accounts와 같은 형식: [{account_id, account_no, alias, balance}]."""
    return copy.deepcopy(_DATA["accounts"].get(customer_id, []))


def debit_check(item: dict, balance: int | None) -> str | None:
    """자동이체 계좌 잔액을 이번에 빠져나가야 할 금액과 비교한 결과 문장. 연체면 연체 금액, 아니면 납부 예정 이자와 비교."""
    if item["payment_method"] != "자동이체" or balance is None:
        return None
    if item["overdue_days"] > 0:
        return "연체 금액보다 적음" if balance < item["overdue_amount"] else "연체 금액 이상"
    return "납부 예정 이자보다 적음" if balance < item["interest_due"] else "납부 예정 이자 이상"


def enrich(item: dict, customer_id: str) -> dict:
    """조회 결과에 자동이체 계좌 비교 결과(debit_status)와 잔액(debit_balance, 슬롯용)을 붙인 사본."""
    account_id = item.get("debit_account_id")
    if not account_id:
        return item
    balance = next((a["balance"] for a in get_accounts(customer_id) if a["account_id"] == account_id), None)
    status = debit_check(item, balance)
    if status is None:
        return item
    return {**item, "debit_status": status, "debit_balance": balance}
