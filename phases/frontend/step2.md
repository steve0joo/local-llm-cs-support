# Step 2: api-client

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (CRITICAL: 프론트엔드는 `/api/chat`만 호출)
- `/docs/ARCHITECTURE.md` (계약 1 채팅 API)
- `/docs/frontend/ARCHITECTURE.md` (타입·API 규칙, 패턴)
- `/docs/frontend/ADR.md` (FE-005 목은 테스트에서만, FE-006 타임아웃 없음)
- step 0 산출물: `/frontend/src/types/chat.ts`, `/frontend/next.config.ts`, `/frontend/vitest.config.ts`

## 작업

수정 가능한 범위는 `frontend/src/lib/`와 `phases/frontend/`뿐이다.

1. `frontend/src/lib/api.test.ts` — **테스트를 먼저** 작성한다. 전역 `fetch`를 목으로 바꾼다(`vi.stubGlobal` 또는 `vi.spyOn(globalThis, "fetch")`, 테스트 뒤 원복). 확인할 것:
   - `POST`로 상대경로 `/api/chat`을 부르고, `Content-Type: application/json` 헤더와 요청 객체를 JSON으로 보낸다
   - `choice`가 없는 요청의 본문에는 `choice` 키 자체가 없다(`"choice" in JSON.parse(body)`가 `false`)
   - `choice: "balance"`가 있는 요청의 본문에는 `choice`가 그대로 들어간다
   - 2xx 응답이면 응답 JSON을 `ChatResponse`로 돌려준다
   - 2xx가 아닌 응답(예: 500, 404)이면 reject한다
   - `fetch` 자체가 reject하면(네트워크 오류) reject한다
2. `frontend/src/lib/api.ts`
   ```ts
   export async function sendChat(req: ChatRequest): Promise<ChatResponse>;
   ```

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/lib/api.test.ts
npx tsc --noEmit
npm run lint
test -z "$(grep -rl 'localhost:8000' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `sendChat`이 상대경로 `/api/chat`만 부르는가? (백엔드 주소는 `next.config.ts`에만)
   - 타임아웃(`AbortController`, `setTimeout`)·재시도가 없는가? (FE-006)
   - 환경변수로 가짜 응답을 돌려주는 분기가 없는가? (FE-005)
   - `git status --short`에 `frontend/src/lib/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `http://localhost:8000`이나 Ollama·mock API 주소를 코드에 쓰지 마라. 이유: CLAUDE.md CRITICAL — 프론트는 `/api/chat`만 호출하고, 백엔드 주소는 rewrites에만 둔다.
- 타임아웃·재시도·런타임 목 모드를 넣지 마라. 이유: FE-005, FE-006.
- `frontend/src/lib/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
