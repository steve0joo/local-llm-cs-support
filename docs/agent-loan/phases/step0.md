# Step 0: mock-api

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (디렉토리 구조, 계약 6 mock 고객 데이터 공통 ID)
- `/docs/ADR.md`
- `/docs/agent-loan/PRD.md`
- `/docs/agent-loan/ARCHITECTURE.md` (mock API·mock 데이터 절)
- `/docs/agent-loan/ADR.md`
- `/docs/agent-interest/ARCHITECTURE.md` (mock 데이터가 `loan_id`·`product_type`을 공유한다)
- `/docs/agent-balance/ARCHITECTURE.md` (비교용 — 같은 구조의 다른 영역)

## 작업

수정 가능한 범위는 `backend/app/agents/loan/`과 `backend/tests/loan/`뿐이다. 이 step은 `agents/base.py`·`llm`·`masking`에 의존하지 않는다(아직 main에 없을 수 있다).

먼저 실행 환경을 확인한다: `python3 -c "import fastapi, httpx, pytest"`가 실패하면 `blocked`로 표시한다(`blocked_reason`: "fastapi·httpx·pytest 미설치 — 팀원C 소유 backend/requirements.txt 기준으로 설치 필요"). 이 step에서 `backend/requirements.txt`를 만들거나 고치지 마라.

1. `backend/tests/loan/test_mock_api_loan.py` — **테스트를 먼저** 작성한다(TDD 가드가 강제한다). 검증 내용:
   - `GET /mock/customers/C002/loans` → `[{"loan_id": "L001", "product_type": "신용대출", "principal_remaining": 12000000, "maturity_date": "2027-03-31", "extendable": true}]`
   - `C003` → `L002` / 주택담보대출 / 85000000 / `2035-06-30` / `extendable: false`
   - `C001`과 모르는 ID(`C999`)는 404가 아니라 `[]`
   - 응답의 어느 항목에도 금리·이율 관련 키가 없다
   - `backend/app/agents/interest/mock_data.json`이 **존재할 때만**: 같은 `loan_id`의 `product_type`이 이 영역과 일치한다(없으면 `pytest.skip`)
2. `backend/app/agents/loan/mock_data.json` — `docs/agent-loan/ARCHITECTURE.md`의 mock 데이터 표 그대로. 키는 customer_id, 값은 대출 배열(`C001`은 `[]`).
3. `backend/app/agents/loan/mock_api.py`
   ```python
   def get_loans(customer_id: str) -> list[dict]: ...   # 모르는 ID면 []
   mock_router: APIRouter                                # GET /mock/customers/{customer_id}/loans
   ```
   - JSON은 모듈 import 시 한 번 읽는다. 호출마다 반환값을 복사해서 돌려준다(호출자가 바꿔도 원본이 오염되지 않게).
4. `backend/app/agents/loan/__init__.py` — 이 step에서는 **주석 한 줄짜리 빈 패키지**로 둔다. `agent`를 export하려면 `agents/base.py`가 필요한데 아직 없다. export는 step 2에서 채운다.

## Acceptance Criteria

```bash
cd backend && python -m pytest tests/loan/test_mock_api_loan.py -q
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 파일이 `backend/app/agents/loan/`, `backend/tests/loan/` 밖에 만들어지지 않았는가?
   - `product_type`이 일반 명칭(신용대출, 주택담보대출)이고 금리 필드가 없는가?
   - 금액은 정수(원), 날짜는 `YYYY-MM-DD` 문자열, `extendable`은 boolean인가?
3. 결과에 따라 `docs/agent-loan/phases/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 테스트 파일 이름을 `test_mock_api.py`로 짓지 마라. 이유: 잔액조회 영역에도 같은 이름이 생기고, `tests/`에 `__init__.py`가 없으면 pytest가 basename 충돌로 수집에 실패한다. 영역 접미사(`_loan`)를 붙인다.
- `mock_data.json`에 금리·이율·연장 불가 사유 필드를 넣지 마라. 이유: 모델이 지어낼 근거를 데이터에서 없애는 것이 설계 원칙이다(LN-002, mock 데이터 절).
- 실제 은행 상품명을 쓰지 마라. 이유: 계약 6 — 일반 명칭만 허용.
- `backend/app/agents/base.py`, `backend/requirements.txt` 등 다른 영역 소유 파일을 만들거나 고치지 마라. 이유: 소유자가 팀원C다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
