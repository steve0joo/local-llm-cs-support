# Step 6: prepare-filter-widen

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터" 절의 **"안전망 필터"** 3~5 — 보강된 BAL-009 단어 목록, 조회 결과 단정, 비식별 표시의 규칙과 빠질·남길 예문)
- `/docs/agent-balance/ADR.md` (BAL-009와 그 "보강" 문단, BAL-010)
- `/backend/training/balance/prepare.py` (step 5 산출물 — `_ASKS_PERSONAL_INFO`·`_PROMISES_ACTION`·`_call_center_answer`, `build_sample`)
- `/backend/tests/balance/test_prepare.py` (step 5 산출물 — BAL-009 빠질·남길 예문 parametrize 테스트의 모양)

## 배경

step 10(사람, train-export)에서 1차 규칙으로 가공본을 다시 만들고 `valid.jsonl` 22건을 읽었다. 그 결과 규칙의 동사·어미 목록 밖 표현이 8건 남아 있었다. 예를 들면 "문자 발송을 바로 진행해 드리겠습니다", "즉시 처리해 드립니다", "성함과 생년월일을 제공해 주셔야"다. 가공본을 점검해 보니 조회 결과를 단정하는 정답("확인 결과 정상 입금되었습니다")과 AI Hub 비식별 표시(`★★은행`, `●월 ●일`)가 남은 정답도 있었다. 사용자 결정에 따라 BAL-009 규칙을 넓히고, 이 두 가지도 뺀다(ADR BAL-009 "보강", BAL-010).

ARCHITECTURE는 최종 모양(`build_samples`, LLM 재작성)을 기술한다. **이 step에서는 기존 `build_sample(qa)`에 제외 규칙만 더한다.** `build_samples`로 바꾸는 것은 step 8이고, 200자 길이 규칙도 step 8에서 넣는다.

## 작업

수정 가능한 범위는 `backend/training/balance/prepare.py`, `backend/tests/balance/test_prepare.py`, `docs/agent-balance/`뿐이다. **실제 AI Hub 데이터로 실행하지 않는다.**

**테스트를 먼저** 작성한다(TDD 가드). 실패를 확인한 뒤 구현한다.

1. `backend/tests/balance/test_prepare.py` — ARCHITECTURE "안전망 필터" 3~5의 예문을 그대로 쓴다.
   - 콜센터식 정답(3): 새로 더한 빠질 예문 9개를 기존 빠질 예문 parametrize에 더한다. 개인정보 요구 1개("먼저 성함과 생년월일을 제공해 주셔야 …")와 행동 약속 8개("문자 발송을 바로 진행해 드리겠습니다"부터 "최근 자동이체 여부를 조회해 드리겠습니다"까지)다. 새 남길 예문 1개("해당 내역은 조회해 드릴 수 없으니 상담원에게 확인해 주세요")는 기존 남길 예문 parametrize에 더한다.
   - 조회 결과 단정(4): 빠질 예문 4개를 `output`으로 둔 QA의 `build_sample`은 `None`이다. 남길 예문 3개는 정답이 그 예문 그대로다.
   - 비식별 표시(5): 빠질 예문 3개를 `output`으로 둔 QA의 `build_sample`은 `None`이다.
   - 기존 테스트는 모두 그대로 통과해야 한다. 그중에서도 `output`에만 적용되는지 보는 테스트가 중요하다.
2. `backend/training/balance/prepare.py`
   - `_ASKS_PERSONAL_INFO` 동사에 `제공해`를 더한다.
   - `_PROMISES_ACTION`은 동사 14개(`보내`·`전송해`·`발급해`·`조치해`·`정정해`·`처리해`·`발송해`·`전달해`·`제공해`·`진행해`·`정리해`·`접수해`·`신청해`·`조회해`)와 어미 `드리겠`·`드리니`·`드립니다`·`드릴 수`로 넓힌다. 동사와 어미 사이 띄어쓰기는 있어도 없어도 잡는다. `드릴 수` 뒤에 `없`이 오면(띄어쓰기 유무 모두) 잡지 않는다. `즉시`·`바로` 뒤의 `진행하겠`·`처리하겠`도 잡는다.
   - 조회 결과 단정 정규식 `_CLAIMS_LOOKUP`과 비식별 표시 정규식 `_DEID_MARK`를 모듈 비공개로 추가한다. 둘 다 `build_sample`의 기존 제외 규칙 뒤에서 마스킹 뒤 `output`에만 적용한다.
   - 공개 시그니처는 바꾸지 않는다. 결정적이어야 하고 `random`을 쓰지 않는다.
3. 문서: 구현 때문에 ARCHITECTURE의 단어 목록이나 예문을 바꿔야 했다면 ARCHITECTURE를 고치고 summary에 `deviation:`으로 적는다. 바꾸지 않았다면 문서는 건드리지 않는다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_prepare.py tests/balance/test_train.py -q)
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 안전망 필터 3~5의 빠질 예문은 모두 빠지고, 남길 예문은 모두 남는가?
   - 판정이 여전히 `output`에만 적용되는가(기존 입력 쪽 표현 테스트 통과)?
   - 합성 샘플 동작이 그대로인가(기존 합성 테스트 통과)?
   - `app.masking`, `training/common/split.py`, `app/agents/balance/`를 고치지 않았는가?
   - `git status --short`에 데이터·가공본이 없는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (추가한 테스트 수, 바뀌거나 새로 만든 정규식 이름 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `build_sample`을 `build_samples`로 바꾸거나 재작성 캐시·첫 턴 샘플·200자 규칙을 넣지 마라. 이유: step 7·8 범위다. 한 step에 섞으면 실패 원인을 가리기 어렵다.
- `확인해 드리겠`·`안내해 드리겠`·`연결해 드리겠`을 행동 약속 규칙에 넣지 마라. 이유: 사용자가 보강 범위에서 뺐고, 안내·연결은 기본 문장과 같은 방향이다(BAL-009).
- 서류·양식 단어(계약서·양식·신청서·요청서)로 빼는 규칙을 추가하지 마라. 이유: 보강 범위에서 제외하기로 결정했다.
- `app/agents/balance/validate.py`(런타임 출력 검증)를 고치지 마라. 이유: 이것은 학습 데이터 결정이고, 런타임 검증을 넓히는 것은 합의되지 않았다.
- 실제 AI Hub 데이터나 가공본을 테스트·저장소에 넣지 마라. 이유: CLAUDE.md CRITICAL 규칙(데이터 커밋 금지)이고, 다른 기기에는 데이터가 없어 테스트가 깨진다.
- `python -m training.balance.prepare`를 실제 경로로 실행하지 마라. 이유: 가공 데이터 재생성과 점검은 step 10(사람) 범위다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
