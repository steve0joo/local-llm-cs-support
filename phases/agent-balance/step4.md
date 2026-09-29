# Step 4: modelfile

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 5 모델 이름)
- `/docs/ADR.md` (ADR-004 Ollama + GGUF)
- `/docs/agent-balance/ARCHITECTURE.md` ("Modelfile (3차)" 절, "테스트로 고정할 핵심 규칙"의 `test_modelfile.py`)
- `/docs/agent-balance/ADR.md` (BAL-006 — 베이스 `Qwen/Qwen3-4B-Instruct-2507`)
- `/backend/app/agents/balance/prompt.py` (`SYSTEM_PROMPT`)
- `/backend/training/balance/prepare.py` (step 3 산출물 — 학습 데이터의 system 메시지가 `SYSTEM_PROMPT`임을 확인)
- 참고(복사하지 말고 형식만 본다): `git show origin/feat-agent-interest:backend/models/interest/Modelfile` — 같은 베이스를 쓰는 팀원B의 ChatML `TEMPLATE`

## 작업

수정 가능한 범위는 `backend/models/balance/`, `backend/tests/balance/`, `docs/agent-balance/`뿐이다.

**테스트를 먼저** 작성한다.

1. `backend/tests/balance/test_modelfile.py` — `backend/models/balance/Modelfile`을 텍스트로 읽어 확인한다.
   - `SYSTEM """..."""` 안의 내용이 `prompt.SYSTEM_PROMPT`와 글자 단위로 같다
   - `FROM ./cs-balance.gguf` 줄이 있다
   - `PARAMETER stop "<|im_end|>"` 줄이 있다
   - `TEMPLATE`에 `<think>`가 없다(생각 블록 없는 ChatML)
2. `backend/models/balance/Modelfile` — ARCHITECTURE "Modelfile (3차)" 절의 항목을 모두 담는다. 파일 머리 주석에 만드는 법(`backend/training/balance/MAC_TRAINING.md`)과 등록 명령(`ollama create cs-balance -f backend/models/balance/Modelfile`)을 적는다.
3. 문서: `docs/agent-balance/ARCHITECTURE.md` 디렉토리 구조의 `models/balance/Modelfile` "3차 예정" 표시와 "Modelfile (3차)" 제목의 "(3차)"를 지운다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_modelfile.py tests/balance/test_prompt.py -q)
test -z "$(git ls-files '*.gguf' '*.safetensors')"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - Modelfile이 `backend/models/balance/`에 있고 모델 이름이 계약 5의 `cs-balance`인가?
   - `.gguf` 파일을 만들거나 스테이징하지 않았는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `prompt.SYSTEM_PROMPT`를 고쳐서 테스트를 맞추지 마라. 이유: step 3 학습 데이터의 system 메시지와 추론 입력이 같아야 한다. Modelfile 쪽을 맞춘다.
- `ollama create`나 모델 다운로드를 실행하지 마라. 이유: GGUF는 step 5(사람)에서 만든다.
- 팀원B의 Modelfile을 통째로 복사하지 마라. 이유: SYSTEM·파일 이름이 다르고, 영역 파일은 각자 소유다. `TEMPLATE` 형식만 참고한다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
