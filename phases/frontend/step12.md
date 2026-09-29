# Step 12: api-response-check

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (CRITICAL: 프론트엔드는 `/api/chat`만 호출)
- `/docs/ARCHITECTURE.md` (계약 1 채팅 API)
- `/docs/frontend/ARCHITECTURE.md` ("타입·API 규칙"의 응답 최소 형식 확인, "에러 처리")
- `/docs/frontend/ADR.md` (FE-005, FE-006)
- `/frontend/src/lib/api.ts`, `/frontend/src/lib/api.test.ts`
- `/frontend/src/components/MessageBubble.tsx`, `/frontend/src/components/OptionButtons.tsx`, `/frontend/src/components/ChatWindow.tsx` (`text`·`slots`·`options`를 어떻게 읽는지)

## 작업

2xx 응답이라도 화면을 깨뜨리는 형식이면 오류로 돌린다. 수정 가능한 범위는 `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `phases/frontend/`뿐이다.

1. `frontend/src/lib/api.test.ts` — 기존 케이스는 그대로 두고 **테스트를 먼저** 추가한다. `fetch`는 기존 테스트처럼 `vi.stubGlobal`로 목을 만들고, 모두 200 응답이다.
   - reject: `text`가 `null` / `text`가 숫자(`123`) / `text` 키 없음 / `options`가 객체(`{}`) / `options`가 문자열(`"a"`)
   - resolve: `options`가 `null` / `options` 키 없음 / 정상 응답(계약 1 형태) — 셋 다 본문 그대로 돌려준다
2. `frontend/src/lib/api.ts` — 시그니처는 그대로 `export async function sendChat(req: ChatRequest): Promise<ChatResponse>`. 본문을 파싱한 뒤 ARCHITECTURE "타입·API 규칙"의 **응답 최소 형식 확인** 규칙대로 throw한다. 형식이 맞으면 본문을 그대로 돌려준다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/lib/api.test.ts
npm run lint
npx tsc --noEmit
npm run build
npm run test
test -z "$(grep -rlE 'localhost:8000|11434|/mock/' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `fetch`는 여전히 `lib/api.ts`의 상대경로 `/api/chat` 한 곳뿐인가?
   - 타임아웃·재시도·런타임 목 분기가 없는가? (FE-005, FE-006)
   - `git status --short`에 `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `slots`나 선택지 항목 안쪽(`label`·`choice` 타입, 슬롯 값 타입)을 검사하지 마라. zod 같은 검증 라이브러리도 추가하지 마라. 이유: 렌더링을 깨뜨리는 것은 `text`와 `options` 두 가지뿐이다. 항목 단위 검증은 게이트웨이 응답 모델이 할 일이다(ARCHITECTURE "타입·API 규칙").
- 응답을 고쳐서 돌려주지 마라(예: `options: null`을 `[]`로 바꾸기). 이유: 확인만 한다. `null`·누락은 화면 코드가 이미 안전하게 처리한다.
- 요청 타임아웃·재시도·환경변수 목 분기를 넣지 마라. 이유: FE-005, FE-006.
- 실제 네트워크를 부르는 테스트를 쓰지 마라. 이유: 백엔드가 없다(FE-005).
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
