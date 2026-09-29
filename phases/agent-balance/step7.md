# Step 7: review

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/agent-balance/PRD.md`, `/docs/agent-balance/ARCHITECTURE.md`, `/docs/agent-balance/ADR.md`
- `/.claude/commands/review.md` (체크리스트 기준)
- `git diff --stat origin/main...HEAD`로 이 브랜치 전체 변경 파일 목록

## 작업

`/.claude/commands/review.md`의 체크리스트 7개 항목으로 `feat-agent-balance` 브랜치의 `origin/main` 대비 diff를 검토한다. 이 step에서는 **코드를 수정하지 않는다**(발견 사항 보고만).

이 영역에서 특히 확인할 것:

- 잔액·거래 금액 원본(`1234567`, `1,234,567`, `2400000` 등)과 전체 계좌번호가 프롬프트·history·합성 샘플 어디에도 들어가지 않는가? mock 값은 `slots`로만 나가는가?
- 출력 검증(BAL-002)을 거치지 않고 모델 출력이 `AgentReply.text`로 나가는 경로가 없는가?
- 테스트가 핵심 규칙을 깨는 입력을 재현하는가: `입출금` 오분류, 본인 아닌 계좌번호 + 별칭, 두 계좌가 함께 걸리는 입력, 숫자·서류·상품명이 든 학습 정답 제외, 합성 샘플의 mock 값 부재, Modelfile SYSTEM 일치. 스모크 테스트만 있으면 ❌
- 수정 범위가 `backend/app/agents/balance/`, `backend/tests/balance/`, `backend/training/balance/`, `backend/models/balance/`, `docs/agent-balance/`, `phases/agent-balance/` 안에 있는가? 아래 알려진 예외 밖의 파일 변경은 ❌
  - 알려진 예외(보고만, 막지 않는다): `backend/tests/router/test_base.py`·`backend/tests/gateway/test_api.py`(ARCHITECTURE "알려진 한계"), `backend/README.md`·`backend/training/requirements.txt`·`.gitignore`·`docs/ADR.md`·`docs/ARCHITECTURE.md`·`docs/PRD.md`(BAL-006 Mac 학습 안내 — 공통 문서라 팀 합의 필요로 보고), `phases/index.json`
- `.gguf`·`.safetensors`·`backend/data/`·`backend/logs/`·`scripts/`·`.ouroboros/`가 커밋에 없는가?

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest -q)
test -z "$(git ls-files '*.gguf' '*.safetensors' backend/data backend/logs scripts .ouroboros)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 리뷰 체크리스트의 `bash scripts/verify.sh`는 파일이 있을 때만 실행한다.
2. 리뷰 결과를 `review.md`의 출력 형식(표)으로 정리해 summary에 담는다. 알려진 예외는 표 아래에 따로 적는다.
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 모든 항목 ✅ → `"status": "completed"`, `"summary": "리뷰 결과 한 줄 요약"`
   - CRITICAL 위반이나 치명 결함 발견 → `"status": "blocked"`, `"blocked_reason": "위반 내용과 수정 방안"` 후 즉시 중단
   - 수정 3회 시도 후에도 AC 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`

## 금지사항

- 리뷰 중에 코드를 고치지 마라. 이유: 리뷰 결과와 수정 이력이 섞이면 무엇이 결함이었는지 추적이 안 된다. 결함은 `blocked`로 보고하고 사람이 pending step을 추가해 고친다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
