# Step 10: rewrite-rules

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터"의 **"LLM 재작성"** 규칙 1~11과 그 아래 "그대로 넣는다" 줄, **"`rewrite.py` 인터페이스"**의 `REWRITE_SYSTEM`, "테스트로 고정할 핵심 규칙"의 `test_rewrite.py`)
- `/docs/agent-balance/ADR.md` (BAL-010과 그 "보강" 문단)
- `/backend/training/balance/rewrite.py` (step 7 산출물 — `REWRITE_SYSTEM`)
- `/backend/tests/balance/test_rewrite.py` (step 7 산출물 — `REWRITE_SYSTEM` 테스트의 모양)

## 배경

step 11(사람, train-export)에서 `rewrite --limit 30` 시범을 돌리고 30건을 원문과 나란히 읽었다. 숫자·가림 표시·200자·조회 결과 단정·개인정보 요구 규칙은 지켰다. 그러나 답 60개 중 약 14개에 문제가 있었다. 원문의 검증되지 않은 사실을 그대로 옮긴 답이 가장 많았다("수수료는 발생하지 않습니다", "휴일이면 전 영업일에 처리"). 한 고객의 조회 결과를 일반 정의로 바꾼 답, 메뉴 이름, 나중에 해 줄 일 약속, 같은 묶음의 다른 item 내용도 있었다. 사용자 결정에 따라 모델(`claude-haiku-4-5`)과 묶음 크기(`CHUNK`)는 그대로 둔다. `REWRITE_SYSTEM`의 규칙 5·7·10을 보강하고 규칙 11을 더한다(ADR BAL-010 "보강").

## 작업

수정 가능한 범위는 `backend/training/balance/rewrite.py`, `backend/tests/balance/test_rewrite.py`, `docs/agent-balance/`뿐이다.

**테스트를 먼저** 작성한다(TDD 가드). 실패를 확인한 뒤 구현한다.

1. `backend/tests/balance/test_rewrite.py` — 아래 문자열이 모두 `rewrite.REWRITE_SYSTEM`에 그대로 들어 있는지 parametrize 테스트 하나로 확인한다. 문자열은 ARCHITECTURE "LLM 재작성" 규칙에서 그대로 옮긴다.
   - 규칙 5 예문 2개: "정확한 원인을 파악하여 안내해 드리겠습니다", "해결되면 문자로 안내하므로 기다려 주세요"
   - 규칙 7 예문 6개: "수수료는 발생하지 않습니다", "출금일이 휴일이면 전 영업일에 처리됩니다", "보류 금액은 자동으로 해제됩니다", "금융보안 관련 규정이 변경되었습니다", "개인 정보 관리 메뉴에서 변경하실 수 있습니다", "지급정지 상태는 해외 결제 등으로 자금이 일시적으로 보류된 상태를 의미합니다"
   - 규칙 10 괄호 안 예시 4개: "앱을 최신 버전으로 업데이트한 뒤 다시 시도", "모바일 앱이나 인터넷 뱅킹에서 거래내역 확인", "송금한 은행이나 카드사에 문의", "비밀번호 정기 변경"
   - 규칙 11 문장 2개: "items는 서로 다른 상담이다", "다른 item의 내용을 가져오지 않는다"
   - 먼저 실행해 실패(red)를 확인한다.
2. `backend/training/balance/rewrite.py` — `REWRITE_SYSTEM`의 규칙 5·7·10을 ARCHITECTURE 문구대로 바꾸고, 규칙 11을 10과 "출력:" 줄 사이에 더한다.
   - 예문은 ARCHITECTURE처럼 큰따옴표로 감싼다. 규칙 문장은 지금 `REWRITE_SYSTEM`의 말투(한 줄에 규칙 하나, "~한다"체)에 맞춘다.
   - 규칙 1~4·6·8·9, "출력:" 줄, `MAX_CHARS`·`DOCUMENT_KEYWORDS`를 상수에서 채우는 방식은 그대로 둔다.
   - `MODEL`·`CHUNK`·`OUTPUT_SCHEMA`·함수들은 바꾸지 않는다.
3. 문서: 구현 때문에 ARCHITECTURE 문구를 바꿔야 했다면 ARCHITECTURE를 고치고 summary에 `deviation:`으로 적는다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_rewrite.py tests/balance/test_prepare.py -q)
(cd backend && .venv/bin/python -c "from training.balance import rewrite; assert '11. ' in rewrite.REWRITE_SYSTEM and 'claude-haiku-4-5' == rewrite.MODEL and rewrite.CHUNK == 20")
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 테스트가 실제 `claude` CLI를 부르지 않는가?
   - 규칙 1~4·6·8·9와 기존 `REWRITE_SYSTEM` 테스트(`MAX_CHARS`·`DOCUMENT_KEYWORDS`·`key`)가 그대로인가?
   - `prepare.py`, `app/`, `training/common/`을 고치지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (바꾼 규칙 번호와 추가한 테스트 수 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `claude` CLI를 실제로 부르거나 `python -m training.balance.rewrite`를 실행하지 마라. 이유: 사용자 구독 사용량을 쓰고, executor 세션 안에서 다시 Claude Code를 띄우게 된다. 재시범은 step 11(사람)이 한다.
- `data/processed/balance/rewrites.jsonl` 캐시를 지우거나 옮기지 마라. 이유: 1차 시범 결과는 사람이 `rewrites.v1.jsonl`로 옮겨 재시범과 비교한다(step 11).
- `MODEL`·`CHUNK`를 바꾸지 마라. 이유: 사용자가 규칙만 보강하기로 했다(BAL-010 보강).
- `prepare.py`의 안전망 필터(정규식)를 더하거나 바꾸지 마라. 이유: 결정적 필터는 재시범 결과를 보고 정한다(BAL-010 보강).
- `qa_key`나 캐시 한 줄 형식을 바꾸지 마라. 이유: 규칙이 바뀌면 사람이 캐시를 옮긴다(ARCHITECTURE "LLM 재작성" 실행 순서). 키에 규칙 버전을 넣는 것은 이번 범위가 아니다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
