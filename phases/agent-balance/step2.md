# Step 2: resolve-typed

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/agent-balance/PRD.md` (사용자 스토리 7, "사용자 여정" J9, "구현 진행" 3차 계획 2)
- `/docs/agent-balance/ARCHITECTURE.md` ("handle() 흐름" 5단계, "대상 계좌 결정 (`resolve.py`)" 규칙 1~6과 규칙 4 예, "3차에 추가할 테스트", "알려진 한계" (c)(d))
- `/docs/agent-balance/ADR.md` (BAL-003 "추가")
- `/backend/app/agents/balance/resolve.py`, `/backend/app/agents/balance/agent.py`
- `/backend/tests/balance/test_resolve.py`, `/backend/tests/balance/test_agent.py`
- `/backend/app/agents/balance/intent.py` (step 1 산출물 — `입출금` 규칙)

## 작업

수정 가능한 범위는 `backend/app/agents/balance/resolve.py`, `backend/app/agents/balance/agent.py`, `backend/tests/balance/test_resolve.py`, `backend/tests/balance/test_agent.py`, `docs/agent-balance/`뿐이다.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/balance/test_resolve.py`
   - 기존 `choose_account` 호출은 세 번째 인자로 masked_text를 넘기게 고친다(기존 기대값은 그대로).
   - ARCHITECTURE "3차에 추가할 테스트"의 `test_resolve.py` 케이스를 추가한다: 규칙 4 예 네 개, C001 + "생활비 계좌 잔액" → A001(규칙 5), C002 + 본인 아닌 `[계좌번호_1]` + "생활비" → 본인 아님 안내(규칙 3이 먼저).
   - 두 계좌가 함께 걸리는 입력(C002 "생활비랑 입출금 계좌 잔액") → `"어느 계좌를 조회할까요?"` 되묻기(규칙 6).
2. `backend/tests/balance/test_agent.py` — 2턴: C002 "잔액 알려줘" → 되묻기 → history를 게이트웨이처럼 채운 뒤 "생활비 계좌 잔액 알려줘" 턴에서 A003 잔액 slots, 모델 호출 1번.
3. `backend/app/agents/balance/resolve.py`
   ```python
   def choose_account(accounts: list[dict], mask_map: dict[str, str], masked_text: str) -> dict: ...
   ```
   - ARCHITECTURE 규칙 4를 규칙 3 뒤, 규칙 5 앞에 넣는다. 후보 = `alias` 또는 `account_no` 끝 4자리가 `masked_text`에 부분 문자열로 들어 있는 **본인 계좌**. 정확히 1개일 때만 그 계좌.
4. `backend/app/agents/balance/agent.py` — `choose_account(accounts, req.mask_map, req.masked_text)`로 호출만 바꾼다.
5. 문서: `docs/agent-balance/ARCHITECTURE.md`의 "※ masked_text 인자는 3차에 추가", 규칙 설명의 "(`masked_text` 인자와 규칙 4는 3차에 추가, 현재 코드는 …)", 규칙 4의 "(3차)" 표시와 `docs/agent-balance/PRD.md` 사용자 스토리 7의 "(3차)"를 지운다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_resolve.py tests/balance/test_agent.py tests/balance/test_intent.py -q)
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 규칙 순서가 ARCHITECTURE 1~6과 같은가(계좌번호 토큰 규칙 2·3이 규칙 4보다 먼저)?
   - `choose_account`가 여전히 plain dict를 돌려주는가(BAL-005)?
   - 모델 입력(`build_messages`)이 바뀌지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (새 시그니처 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 규칙 4에서 다른 고객의 계좌나 `mask_map` 원본을 보지 마라. 이유: 규칙 4는 이미 화면 라벨로 보이는 별칭·끝 4자리만 본인 계좌와 맞춘다. 계좌번호 원본 비교는 규칙 2만 한다(계약 3 — mask_map은 Python 비교 전용).
- `find_clicked`를 바꾸거나 직전 계좌 이어가기를 넣지 마라. 이유: 이어가기(J10)는 2026-09-29 결정으로 하지 않는다(알려진 한계 (c)).
- 별칭 매칭을 형태소 분석·유사도·정규화로 넓히지 마라. 이유: MVP — 부분 문자열 일치만 쓴다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
