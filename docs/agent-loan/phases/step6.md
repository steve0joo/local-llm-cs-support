# Step 6: review

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (없으면 이 항목은 건너뛰고 요약에 "CLAUDE.md 없음"이라 적는다)
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/agent-loan/PRD.md`, `/docs/agent-loan/ARCHITECTURE.md`, `/docs/agent-loan/ADR.md`
- `/.claude/commands/review.md` (체크리스트 기준)
- `git diff --stat main...HEAD`로 이 phase 전체 변경 파일 목록

## 작업

`/.claude/commands/review.md`의 체크리스트 7개 항목으로 `feat-agent-loan` 브랜치의 phase 전체 diff를 검토한다. 이 step에서는 **코드를 수정하지 않는다**(발견 사항 보고만).

이 영역에서 특히 확인할 것:

- 원금 숫자(`12000000`, `85000000`)가 프롬프트·history·학습 데이터 산출물 어디에도 들어가지 않는가?
- 출력 검증이 허용 목록 방식(LN-004)이고, 검증을 우회하는 경로가 없는가?
- 테스트가 핵심 규칙을 깨는 입력(금리·서류·허용 밖 슬롯·다른 날짜·연장 불가 모순·대출 없음 시 모델 미호출)을 재현하는가? 스모크 테스트만 있으면 ❌
- 수정 범위가 `backend/app/agents/loan/`, `backend/tests/loan/`, `backend/training/loan/`, `backend/models/loan/`, `docs/agent-loan/`(step 파일 `docs/agent-loan/phases/` 포함) 안에 있는가? 밖의 파일 변경은 ❌
- `.gguf`·`.safetensors`·`backend/data/`·`backend/logs/`·실제 데이터가 커밋에 없는가?

## Acceptance Criteria

```bash
cd backend && python -m pytest tests/loan -q
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 그리고 리뷰 체크리스트의 `bash scripts/verify.sh`는 파일이 존재할 때만 실행한다.
2. 리뷰 결과를 `review.md`의 출력 형식(표)으로 정리해 summary에 담는다.
3. 결과에 따라 `docs/agent-loan/phases/index.json`의 해당 step을 업데이트한다:
   - 모든 항목 ✅ → `"status": "completed"`, `"summary": "리뷰 결과 한 줄 요약"`
   - CRITICAL 위반이나 치명 결함 발견 → `"status": "blocked"`, `"blocked_reason": "위반 내용과 수정 방안"` 후 즉시 중단
   - 수정 3회 시도 후에도 AC 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`

## 금지사항

- 리뷰 중에 코드를 고치지 마라. 이유: 리뷰 결과와 수정 이력이 섞이면 무엇이 결함이었는지 추적이 안 된다. 결함은 `blocked`로 보고하고 사람이 pending step을 추가해 고친다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
