# Step 9: review

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (없으면 이 항목은 건너뛰고 요약에 "CLAUDE.md 없음"이라 적는다)
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/frontend/PRD.md`, `/docs/frontend/ARCHITECTURE.md`, `/docs/frontend/ADR.md`, `/docs/frontend/UI_GUIDE.md`
- `/.claude/commands/review.md` (체크리스트 기준)
- `git diff --stat main...HEAD`로 이 phase 전체 변경 파일 목록

## 작업

`/.claude/commands/review.md`의 체크리스트 7개 항목으로 `feat-frontend` 브랜치의 phase 전체 diff를 검토한다. 이 step에서는 **코드를 수정하지 않는다**(발견 사항 보고만).

이 영역에서 특히 확인할 것:

- 프론트가 `/api/chat`만 부르는가? `src/`에 `localhost:8000`·Ollama(`11434`)·mock API(`/mock/`) 주소가 없고, 백엔드 주소는 `next.config.ts` rewrites에만 있는가? (CLAUDE.md CRITICAL)
- 슬롯 치환이 `fillSlots` 한 곳에서만 일어나고, 고객 말풍선은 치환하지 않고, `dangerouslySetInnerHTML`이 없는가?
- 런타임 목 모드(FE-005)·요청 타임아웃과 재시도(FE-006)가 없고, `next.config.ts`에 `experimental.proxyTimeout: 120_000`과 `agentRules: false`가 있는가?
- 테스트가 핵심 규칙을 깨는 입력을 재현하는가? 스모크 테스트만 있으면 ❌. 최소한 다음이 있어야 한다:
  - fillSlots: 누락·빈 값·빈 이름·상속 속성 이름·재치환 금지
  - api: 직접 입력 요청에 `choice` 키 없음, 2xx 아님과 네트워크 오류 시 reject
  - ChatWindow: 최신의 오류가 아닌 봇 메시지만 선택지 활성, pending이면 모두 비활성, 공백 입력 차단
  - page: 잔액 목 응답에서 `1,234,567원`이 보이고 `{{` 없음, clarify 선택 요청에 `choice`, 고객 변경 시 새 `session_id`와 초기화
- UI_GUIDE 금지 사항(`backdrop-blur`, `bg-gradient`·`bg-clip-text`, `purple`·`indigo`·`violet`, 글로우 그림자, "Powered by AI")이 `src/`에 없는가?
- 수정 범위가 `frontend/`, `phases/frontend/` 안에 있는가? `phases/index.json`은 execute.py가 다시 쓰면서 생긴 끝 줄바꿈 변경만 허용한다. 그 밖의 파일 변경(`docs/` 공통, `docs/agent-*`, `backend/`, `CLAUDE.md`, `.claude/`)은 ❌
- `frontend/AGENTS.md`·`frontend/CLAUDE.md`·`node_modules/`·`.next/`·`.env*`가 커밋에 없는가?

## Acceptance Criteria

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
npm run test
test -z "$(grep -rlE 'localhost:8000|11434|/mock/|dangerouslySetInnerHTML' src || true)"
test ! -e AGENTS.md
test ! -e CLAUDE.md
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 리뷰 체크리스트의 `bash scripts/verify.sh`는 파일이 있을 때만 실행한다.
2. 리뷰 결과를 `review.md`의 출력 형식(표)으로 정리해 summary에 담는다.
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 모든 항목 ✅ → `"status": "completed"`, `"summary": "리뷰 결과 한 줄 요약"`
   - CRITICAL 위반이나 치명 결함 발견 → `"status": "blocked"`, `"blocked_reason": "위반 내용과 수정 방안"` 후 즉시 중단
   - 수정 3회 시도 후에도 AC 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`

## 금지사항

- 리뷰 중에 코드를 고치지 마라. 이유: 리뷰 결과와 수정 이력이 섞이면 무엇이 결함이었는지 추적이 안 된다. 결함은 `blocked`로 보고하고 사람이 pending step을 추가해 고친다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
