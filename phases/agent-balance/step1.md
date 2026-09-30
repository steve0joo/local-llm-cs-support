# Step 1: intent-alias

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/agent-balance/PRD.md` ("사용자 여정" J8, "구현 진행" 3차 계획 1)
- `/docs/agent-balance/ARCHITECTURE.md` ("의도 판단 (`intent.py`)" 절, "테스트로 고정할 핵심 규칙"의 `test_intent.py`·"3차에 추가할 테스트", "알려진 한계" (b))
- `/docs/agent-balance/ADR.md` (BAL-001, BAL-004)
- `/backend/app/agents/balance/intent.py`, `/backend/tests/balance/test_intent.py`

## 작업

수정 가능한 범위는 `backend/app/agents/balance/intent.py`, `backend/tests/balance/test_intent.py`, `docs/agent-balance/`뿐이다.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/balance/test_intent.py`에 추가한다.
   - ARCHITECTURE "의도 판단" 표의 3차 예문 세 개: "입출금 계좌 잔액 알려줘" → `"balance"`, "입출금 ****6789" → `"balance"`, "입출금 내역 보여줘" → `"transactions"`
   - 회귀 방지: "출금 내역 보여줘" → `"transactions"`, "어제 출금된 거 뭐예요?" → `"transactions"`
2. `backend/app/agents/balance/intent.py`
   ```python
   def classify_intent(question: str) -> str: ...   # 시그니처 그대로
   ```
   - 거래내역 키워드를 검사할 때만 질문에서 `"입출금"`을 모두 지운 문자열을 쓴다. general 판단(1번 규칙)은 원래 질문으로 한다.
3. 문서: `docs/agent-balance/ARCHITECTURE.md` "의도 판단" 절의 "(3차에 추가, 현재 코드는 지우지 않는다)"와 표의 "(3차)" 표시를 지우고, "알려진 한계" (b)의 `입출금 ****6789` 설명을 현재 동작(balance)으로 고친다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_intent.py tests/balance/test_agent.py -q)
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `classify_intent`의 시그니처와 반환값 세 가지가 그대로인가?
   - 단어 목록 상수(`PROCEDURE_WORDS`·`LOOKUP_WORDS`·`TRANSACTION_WORDS`)를 바꾸지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `TRANSACTION_WORDS`에서 `"출금"`을 빼지 마라. 이유: "출금 내역"·"출금된 거"는 거래내역이어야 한다. `입출금`만 별칭으로 예외 처리한다.
- 자체 점검 셋 근거 없이 단어를 추가하지 마라. 이유: 단어 목록은 자체 점검 셋에서 나온 표현만 늘린다(BAL-001, 알려진 한계 (e)).
- `resolve.py`·`agent.py`를 고치지 마라. 이유: 계좌 결정은 step 2 범위다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
