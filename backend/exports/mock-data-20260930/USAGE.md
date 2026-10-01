# 목업 데이터 전달본

기준일: 2026-09-30

## 포함 범위

이 전달본은 관심사 에이전트와 잔액조회 에이전트가 현재 사용하는 목업 데이터 및 조회 방법의 사본입니다. 원본 코드는 변경하지 않았습니다.

- `app/agents/interest/mock_data.json`: 고객별 이자·연체 조회값
- `app/agents/interest/mock_api.py`: `get_interest(customer_id)`와 `/mock/customers/{customer_id}/interest`
- `app/agents/balance/mock_data.json`: 고객별 계좌·거래내역
- `app/agents/balance/mock_api.py`: `get_accounts(customer_id)`, `get_transactions(account_id, limit)` 및 mock 라우트
- `app/agents/interest/balance_source.py`: 관심사 에이전트가 잔액조회 `get_accounts`를 호출해 자동이체 잔액을 비교하는 연결부
- `app/agents/interest/balance_mock.json`: 병합 전 호환용 잔액 목업 사본. 현재 런타임은 사용하지 않음

## 사용 방법

```python
from app.agents.interest.mock_api import get_interest
from app.agents.balance.mock_api import get_accounts, get_transactions

interest = get_interest("C002")
accounts = get_accounts("C002")
transactions = get_transactions("A002", limit=5)
```

고객 ID 또는 계좌 ID가 없으면 조회 함수는 빈 리스트를 반환합니다. FastAPI에서는 다음 mock 라우트가 등록됩니다.

- `GET /mock/customers/{customer_id}/interest`
- `GET /mock/customers/{customer_id}/accounts`
- `GET /mock/accounts/{account_id}/transactions?limit=5`

## 현재 데모 고객

- 관심사: C001~C003
- 잔액조회: C001~C003
- C004~C007은 이번 전달본에서 제외했습니다.

## 병합 시 주의

관심사 영역의 자동이체 잔액 비교는 `balance_source.py`의 `get_accounts` import를 통해 잔액조회 영역을 사용합니다. 잔액 목업을 교체할 때는 `account_id`와 `balance` 필드 호환성을 유지해야 합니다.

파인튜닝 모델과 데이터셋은 이 전달본에 포함하지 않았습니다.
