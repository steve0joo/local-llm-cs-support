# Step 5: prepare-filter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 4 마스킹 토큰)
- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터" 절의 전처리 순서와 **"콜센터식 정답 제외(BAL-009)"** 항목 — 규칙·빠질 예문·남길 예문의 기준, "`prepare.py` 인터페이스", "테스트로 고정할 핵심 규칙"의 `test_prepare.py`)
- `/docs/agent-balance/ADR.md` (BAL-008, BAL-009)
- `/backend/training/balance/prepare.py` (step 3 산출물 — `build_sample`의 기존 제외 규칙 두 가지)
- `/backend/tests/balance/test_prepare.py` (step 3 산출물 — `test_build_sample_excludes_bad_outputs`·`test_build_sample_keeps_generic_or_mentioned_product_names`의 모양)
- `/backend/training/balance/train.py` (`--mask-prompt` — loss가 마지막 assistant 답에만 걸리는 이유)

## 배경

step 6(사람)에서 실제 `valid.jsonl`을 읽다가, AI Hub 정답이 콜센터 상담원 답변이라 챗봇이 하면 안 되는 문장이 섞여 있음을 확인했다. 고객에게 비밀번호·생년월일을 알려 달라고 하거나, 문자 발송·발급처럼 챗봇이 할 수 없는 행동을 약속하는 문장이다. 런타임 출력 검증(`validate.is_valid`)은 이런 문장을 거르지 않는다. 그래서 학습 정답에서 뺀다(BAL-009).

## 작업

수정 가능한 범위는 `backend/training/balance/prepare.py`, `backend/tests/balance/test_prepare.py`, `docs/agent-balance/`뿐이다. **실제 AI Hub 데이터로 실행하지 않는다.** 가공 데이터 재생성은 step 6(사람)이 한다.

**테스트를 먼저** 작성한다(TDD 가드). 실패를 확인한 뒤 구현한다.

1. `backend/tests/balance/test_prepare.py` — ARCHITECTURE "학습 데이터" → "콜센터식 정답 제외(BAL-009)"의 예문을 그대로 쓴다.
   - 빠질 예문 7개: 각각을 `output`으로 둔 QA의 `build_sample`이 `None`이다. 기존 `test_build_sample_excludes_bad_outputs`처럼 parametrize로 만든다.
   - 남길 예문 4개: 각각을 `output`으로 둔 QA의 `build_sample` 정답(마지막 assistant)이 그 예문 그대로다.
   - 입력에만 있는 표현: `follow_up`(또는 `answer`)에 "계좌 번호를 알려드릴게요"처럼 개인정보 요구 표현이 있고 `output`은 `OK_OUTPUT`인 QA는 남는다. 규칙은 `output`에만 적용된다.
2. `backend/training/balance/prepare.py` — `build_sample`에 BAL-009 제외를 더한다. 기존 두 제외 규칙(`is_valid`, 상품명) 뒤에 둔다. 공개 함수 시그니처는 바꾸지 않는다. 판정 헬퍼와 정규식은 모듈 비공개(`_` 접두)로 둔다.

   핵심 규칙(어기면 안 된다):
   - 판정 대상은 마스킹 뒤 `output` 하나뿐이다. `question`·`answer`·`follow_up`에는 적용하지 않는다. 이유: 학습은 `--mask-prompt`라 입력 쪽 문장은 loss에 들지 않는다. 그리고 고객 질문에는 "계좌번호 알려드릴게요" 같은 표현이 정상적으로 나온다.
   - 단어 목록과 거리(같은 문장 25자 안)는 ARCHITECTURE 항목을 따른다. 상담원·담당 부서 "연결해 드리겠습니다"와 "안내해 드리겠습니다"는 빼지 않는다.
   - 결정적이어야 한다. `random`을 쓰지 않는다.
3. 문서: 구현 때문에 ARCHITECTURE의 단어 목록이나 예문을 바꿔야 했다면 ARCHITECTURE를 고치고 summary에 `deviation:`으로 적는다. 바꾸지 않았다면 문서는 건드리지 않는다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_prepare.py tests/balance/test_train.py -q)
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - BAL-009 판정이 `output`에만 적용되는가(입력 쪽 표현 테스트로 확인)?
   - 기존 제외 규칙 두 가지와 합성 샘플 동작이 그대로인가(기존 `test_prepare.py` 전부 통과)?
   - `app.masking`, `training/common/split.py`, `app/agents/balance/`를 고치지 않았는가?
   - `git status --short`에 데이터·가공본이 없는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (추가한 테스트 수, 헬퍼·정규식 이름 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `app/agents/balance/validate.py`(런타임 출력 검증)를 고치지 마라. 이유: BAL-009는 학습 데이터 결정이다. 런타임 검증을 넓히면 합성 응답·기존 테스트·BAL-002 범위까지 바뀌는데, 이는 합의되지 않았다.
- "조회 결과 단정"(예: "정상적으로 처리되었습니다") 문장을 빼는 규칙을 추가하지 마라. 이유: 오탐이 많고 데이터가 크게 줄어서 BAL-009에서 거르지 않기로 했다. step 7 자체 점검 Q8로 확인한다.
- 실제 AI Hub 데이터나 가공본을 테스트·저장소에 넣지 마라. 이유: 데이터셋 이용조건상 제3자 제공 금지이고(CLAUDE.md CRITICAL), 다른 기기에는 데이터가 없다.
- `python -m training.balance.prepare`를 실제 경로로 실행하지 마라. 이유: 가공 데이터 재생성과 점검은 step 6(사람) 범위다.
- `training/common/split.py`, `app/masking/`을 고치지 마라. 이유: 팀원C 소유다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
