# Step 7: rewrite

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 4 마스킹 토큰)
- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터"의 **"LLM 재작성"** 항목, **"`prepare.py` 인터페이스"**의 `REWRITE_PATH`·`mask_fields`·`qa_key`·`load_rewrites`, **"`rewrite.py` 인터페이스"** 전체, "테스트로 고정할 핵심 규칙"의 `test_rewrite.py`)
- `/docs/agent-balance/ADR.md` (BAL-010)
- `/backend/training/balance/prepare.py` (step 6 산출물 — `load_qas`·`normalize_amounts`·`build_sample`)
- `/backend/tests/balance/test_prepare.py` (tmp_path 합성 zip·split.json 픽스처 모양)
- `/backend/training/common/split.py` (`OUT_PATH`·`TL_ZIP`·`VL_ZIP`)

## 배경

AI Hub 정답은 콜센터 상담원 답변이다. 필터만으로는 지어낸 메뉴·절차를 걸러낼 수 없고, 버려지는 데이터도 많다. 그래서 LLM(Claude Haiku 4.5)으로 챗봇 답변으로 다시 쓴다(BAL-010). 호출은 API가 아니라 Claude Code 헤드리스 모드(`claude -p`)로 한다. 이 step은 CLI 호출 명령과 입력을 만들고, 결과를 캐시에 쌓는 코드만 만든다. **실제 `claude` CLI는 부르지 않는다.** 실행은 step 10(사람)이 한다.

## 작업

수정 가능한 범위는 `backend/training/balance/prepare.py`, `backend/training/balance/rewrite.py`(새 파일), `backend/tests/balance/test_prepare.py`, `backend/tests/balance/test_rewrite.py`(새 파일), `docs/agent-balance/`뿐이다.

**테스트를 먼저** 작성한다(TDD 가드). 실패를 확인한 뒤 구현한다.

1. `prepare.py`에 캐시 공용부를 더한다(인터페이스 절 그대로).
   - `REWRITE_PATH`와 `MAX_CHARS = 200`
   - `mask_fields(qa)`: 네 필드 각각 `normalize_amounts` → `mask().masked_text`. 기존 `build_sample`도 이 함수를 쓰도록 바꾼다(동작은 같아야 한다).
   - `qa_key(qa)`: `source_id`와 원문 네 필드를 이은 문자열의 sha256 hex 앞 32자. 이어 붙일 때는 필드 경계가 섞이지 않게 구분자(예: `"\x1f"`)를 넣는다.
   - `load_rewrites(path)`: 파일이 없으면 `{}`. 한 줄마다 `{key: {"answer", "output"}}`로 모은다. 같은 키가 여러 줄이면 마지막 줄을 쓴다.
   - 테스트(`test_prepare.py`): `mask_fields`가 원본 계좌번호를 남기지 않는다. `qa_key`는 같은 입력에 같은 값을 내고, 한 필드만 달라도 다른 값을 낸다. 값은 32자 hex다. `load_rewrites`는 없는 파일에 `{}`을 돌려주고, 중복 키에서는 마지막 줄을 쓴다.
2. `backend/training/balance/rewrite.py`를 인터페이스 절 그대로 만든다: `MODEL`·`CHUNK`·`REWRITE_SYSTEM`·`OUTPUT_SCHEMA`·`build_prompt`·`build_command`·`parse_envelope`·`run_claude`·`split_qas`·`run_all`·`main`.
   - `REWRITE_SYSTEM`은 한국어로 쓰고, ARCHITECTURE "LLM 재작성" 규칙 1~10을 빠짐없이 담는다. "입력 items마다 key를 그대로 돌려준다"도 넣는다. 200자는 `prepare.MAX_CHARS` 값으로 채운다.
   - 외부 의존성을 더하지 않는다(표준 라이브러리 `subprocess`·`tempfile`·`concurrent.futures`만). `run_claude`는 빈 임시 폴더를 `cwd`로 쓰고, 실패·시간 초과면 `""`를 돌려준다.
   - `run_all`: 캐시 파일 쓰기는 메인 스레드에서만 한다. 묶음 결과는 `key`로 QA와 맞춘다(응답 순서를 믿지 않는다).
   - `main`: `split_qas(OUT_PATH, [TL_ZIP, VL_ZIP])` 중 캐시에 없는 QA를 앞에서 `--limit`개 골라 `run_all`에 넘기고 집계를 출력한다. 보낼 것이 없으면 그렇게 출력하고 끝낸다.
3. `backend/tests/balance/test_rewrite.py` — `run`에 가짜 함수를 넣는다. 받은 명령·입력을 기록하고, `--output-format json` 모양의 결과 문자열을 돌려주게 한다. 다음을 확인한다.
   - `build_command`: `claude`·`-p`로 시작한다. `--model` 다음이 인자 모델이다. `--tools` 다음이 빈 문자열이다. `--json-schema` 다음이 `OUTPUT_SCHEMA`의 JSON이다. `--output-format json`·`--no-session-persistence`가 있다. `--system-prompt` 다음이 `REWRITE_SYSTEM`이다.
   - `build_prompt`: items의 key가 `prepare.qa_key`와 같고, 필드는 `mask_fields` 값이다. 원본 계좌번호·전화번호가 없다.
   - `REWRITE_SYSTEM`에 `MAX_CHARS` 값과 `validate.DOCUMENT_KEYWORDS`의 단어가 모두 들어 있다(규칙과 코드 상수가 어긋나지 않게).
   - `parse_envelope`: 정상 결과는 요청한 key의 두 답과 `total_cost_usd`를 돌려준다. 다음 경우는 모두 `({}, 0.0)`이다: JSON이 아닌 문자열, 빈 문자열, `is_error: true`, `structured_output` 없음. 요청하지 않은 key와 빈 answer·output 항목은 버린다.
   - `run_all`: 캐시에 있는 key는 보내지 않는다. `chunk=2`로 QA 5개를 주면 `run`이 3번 불린다. 응답 순서가 달라도 key로 저장한다. 응답에서 빠진 key는 `missing`으로 센다. 캐시 한 줄은 `{"key", "source", "answer", "output"}`이고 `prepare.load_rewrites`로 다시 읽힌다. `jobs=2`로 돌려도 저장된 key 집합이 같다. `cost_usd`는 결과들의 합이다.
   - `split_qas`: split.json에 없는 상담은 빠진다(기존 합성 zip 픽스처를 재사용하거나 같은 방식으로 만든다).
4. 문서: 구현 때문에 인터페이스를 바꿔야 했다면 ARCHITECTURE를 고치고 summary에 `deviation:`으로 적는다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_prepare.py tests/balance/test_rewrite.py tests/balance/test_train.py -q)
(cd backend && .venv/bin/python -c "import training.balance.rewrite")
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 테스트가 실제 `claude` CLI를 부르지 않는가(가짜 `run`만 쓰는가)?
   - CLI로 보내는 텍스트가 모두 `mask_fields`를 거쳤는가?
   - `prepare`가 `rewrite`를 import하지 않는가(한 방향 import)?
   - 기존 `build_sample` 동작과 테스트가 그대로인가?
   - `app/`, `training/common/`을 고치지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (추가한 함수·테스트 수 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `claude` CLI를 실제로 부르거나 `python -m training.balance.rewrite`를 실행하지 마라. 이유: 사용자 구독 사용량을 쓰고, executor 세션 안에서 다시 Claude Code를 띄우게 된다. 실행은 step 10(사람)이 시범 30건부터 한다.
- `anthropic` SDK나 새 패키지를 의존성에 더하지 마라. 이유: 재작성은 Claude Code CLI로 하기로 했다(BAL-010). 런타임 `requirements.txt`도 바뀌면 안 된다.
- `build_sample`을 `build_samples`로 바꾸거나 `build_dataset`이 캐시를 읽게 하지 마라. 이유: step 8 범위다.
- `app/llm`의 `generate()`를 재작성에 쓰지 마라. 이유: `generate()`는 런타임 Ollama 호출 전용이다. 재작성은 학습용 외부 호출이다(BAL-010).
- `--bare`를 명령에 넣지 마라. 이유: `--bare`는 API 키 인증만 받아서 구독 로그인으로 돌 수 없다.
- 실제 AI Hub 데이터나 가공본을 테스트·저장소에 넣지 마라. 이유: CLAUDE.md CRITICAL 규칙(데이터 커밋 금지)이고, 다른 기기에는 데이터가 없어 테스트가 깨진다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
