# Step 8: prepare-rewrite

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터"의 대화 모양·전처리 순서·**안전망 필터 1~6**, "`prepare.py` 인터페이스"의 `build_samples`·`build_dataset`·`main`, "테스트로 고정할 핵심 규칙"의 `test_prepare.py`)
- `/docs/agent-balance/ADR.md` (BAL-008, BAL-009, BAL-010)
- `/backend/training/balance/prepare.py` (step 7 산출물 — `mask_fields`·`qa_key`·`load_rewrites`·`build_sample`·`build_dataset`)
- `/backend/training/balance/rewrite.py` (step 7 산출물 — 캐시 한 줄 형식)
- `/backend/tests/balance/test_prepare.py`

## 배경

step 7로 재작성 결과를 캐시에 쌓을 수 있게 되었다. 이 step에서는 `prepare`가 원문 대신 캐시의 다시 쓴 답을 학습 정답으로 쓰게 한다. QA 하나에서 첫 턴 샘플(`[question] → answer`)과 이어진 턴 샘플을 만든다(BAL-010). 첫 턴 샘플은 history 없는 general 질문(자체 점검 Q6~Q8)과 모양이 같다.

## 작업

수정 가능한 범위는 `backend/training/balance/prepare.py`, `backend/tests/balance/test_prepare.py`, `docs/agent-balance/`뿐이다. **실제 AI Hub 데이터와 실제 캐시로 실행하지 않는다.**

**테스트를 먼저** 작성한다(TDD 가드). 실패를 확인한 뒤 구현한다.

1. `build_sample(qa)`를 `build_samples(qa, rewrite)`로 바꾼다(인터페이스 절 그대로).
   - `rewrite`가 `None`이면 `[]`.
   - `mask_fields(qa)`로 question·follow_up을 얻는다. 다시 쓴 `answer`·`output`에도 `mask()`를 적용한다.
   - 첫 턴 `build_messages([], question, "general") + [assistant: answer]`, 이어진 턴 `build_messages([user: question, assistant: answer], follow_up, "general") + [assistant: output]`. 순서는 첫 턴, 이어진 턴이다.
   - 안전망 필터 1~6을 한 헬퍼(예: `_rejected(target, inputs)`)로 모아 각 목표 답에 따로 적용한다. 상품명 휴리스틱의 입력은 첫 턴이면 `(question,)`, 이어진 턴이면 `(question, answer, follow_up)`이다. 길이 규칙은 `len(target) > MAX_CHARS`면 제외다.
   - 원문 `qa["answer"]`·`qa["output"]`은 목표 답에도 history에도 쓰지 않는다.
2. `build_dataset(split_path, out_dir, zip_paths, rewrites_path=REWRITE_PATH)`는 `load_rewrites(rewrites_path)`로 캐시를 읽고, QA마다 `build_samples(qa, rewrites.get(qa_key(qa)))`의 결과를 그 분할에 더한다. 합성 샘플은 지금처럼 뒤에 붙인다. 반환값(분할별 기록 수)의 모양은 그대로다.
3. `main`에 `--rewrites`(기본 `REWRITE_PATH`)를 더한다. 분할별 기록 수에 더해 "재작성 없음으로 빠진 QA 수"도 출력한다. 계산이 필요하면 모듈 비공개 헬퍼를 둔다. `build_dataset`의 반환 모양은 바꾸지 않는다.
4. 테스트(`test_prepare.py`) — 기존 `build_sample` 테스트는 `build_samples`와 재작성 dict로 옮긴다. 기존 제외 예문들은 이제 다시 쓴 답에 넣어 확인한다.
   - 재작성이 없는 QA는 샘플이 0개다. `build_dataset`에서도 캐시에 없는 QA는 결과 파일에 없다.
   - 두 목표가 모두 통과하면 샘플 2개다. 첫 턴은 역할 `[system, user, assistant]`이고 마지막이 다시 쓴 answer다. 이어진 턴은 `[system, user, assistant, user, assistant]`이고, history assistant가 다시 쓴 answer, 마지막이 다시 쓴 output이다.
   - 목표별 독립 판정: answer만 걸리면 이어진 턴 1개만 남는다(history의 answer는 판정하지 않는다). output만 걸리면 첫 턴 1개만 남는다.
   - 기존 안전망 필터 예문(숫자·서류·상품명·BAL-009·조회 단정·비식별 표시)을 다시 쓴 output에 넣으면 이어진 턴이 빠진다. 201자 답은 빠지고 200자 답은 남는다.
   - 다시 쓴 답에 전화번호 원본을 넣어도 결과 파일에 원본 문자열이 없다(`mask()` 적용).
   - 원문 answer·output에만 있는 고유 문구가 결과 파일 어디에도 없다.
   - `build_dataset` 결과가 `train.check_dataset`을 통과한다(기존 형식 테스트 유지). CLI `--rewrites`가 동작한다.
5. 문서: 구현 때문에 인터페이스를 바꿔야 했다면 ARCHITECTURE를 고치고 summary에 `deviation:`으로 적는다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_prepare.py tests/balance/test_rewrite.py tests/balance/test_train.py -q)
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 목표 답이 모두 캐시의 다시 쓴 답이고, 원문 answer·output이 결과에 섞이지 않는가?
   - 목표 답마다 안전망 필터 1~6이 따로 적용되는가?
   - 합성 샘플 동작과 `rewrite.py` 테스트가 그대로인가?
   - `prepare`가 `rewrite`를 import하지 않는가?
   - `app/`, `training/common/`을 고치지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (바뀐 함수, 추가·수정한 테스트 수 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 재작성 결과가 없을 때 원문 answer·output으로 대신하지 마라. 이유: 원문은 콜센터 말투라 BAL-010이 막으려는 행동을 다시 배운다. 캐시가 없으면 AI Hub 샘플이 0개인 것이 맞다.
- 합성 샘플(질문·응답 목록)을 바꾸지 마라. 이유: step 9 범위다.
- `rewrite.py`를 부르거나 네트워크를 쓰지 마라. 이유: `prepare`는 캐시만 읽어 결정적이어야 한다.
- 실제 AI Hub 데이터나 가공본·캐시를 테스트·저장소에 넣지 마라. 이유: CLAUDE.md CRITICAL 규칙(데이터 커밋 금지)이고, 다른 기기에는 데이터가 없어 테스트가 깨진다.
- `python -m training.balance.prepare`를 실제 경로로 실행하지 마라. 이유: 가공 데이터 재생성과 점검은 step 10(사람) 범위다.
- 기존 테스트의 의도를 없애지 마라. `build_samples`로 옮기되 확인하던 규칙은 그대로 확인한다
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
