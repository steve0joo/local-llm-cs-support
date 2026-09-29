# Step 16: landing-page

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (CRITICAL: 프론트엔드는 `/api/chat`만 호출)
- `/docs/ARCHITECTURE.md` (계약 1 채팅 API, 계약 6 데모 고객 ID)
- `/docs/frontend/PRD.md` (사용자 스토리, "챗 섹션", 인수 기준)
- `/docs/frontend/ARCHITECTURE.md` (패턴, 데이터 흐름, 상태 관리의 `reset`, "화면 동작 규칙"의 연타·새 대화, "랜딩 엔진 통합"의 겹침)
- `/docs/frontend/ADR.md` (FE-002, FE-007, FE-009)
- `/docs/frontend/UI_GUIDE.md` ("챗 섹션", "챗 패널 상단", "새 대화 버튼", h1 규칙)
- 이전 step 산출물: `/frontend/src/components/ScrollWorld.tsx`(step 13), `/frontend/src/components/ChatWindow.tsx`(step 15), `/frontend/src/lib/api.ts`(step 12), `/frontend/src/app/globals.css`·`layout.tsx`(step 11)
- `/frontend/src/app/page.tsx`, `/frontend/src/app/page.test.tsx`

## 작업

랜딩과 챗 섹션을 한 페이지로 조립하고 "새 대화"를 넣는다. 수정 가능한 범위는 `frontend/src/app/page.tsx`, `frontend/src/app/page.test.tsx`, `phases/frontend/`뿐이다.

1. `frontend/src/app/page.test.tsx` — **테스트를 먼저** 작성한다.
   - 파일 위쪽에 `vi.mock("../components/ScrollWorld", () => ({ ScrollWorld: () => null }))`를 추가한다. 기존 5개 케이스는 고치지 않는다.
   - 추가할 케이스:
     - `document.getElementById("chat")` 섹션이 있다. 그 안에 메시지 입력창, 데모 고객 선택, "새 대화" 버튼, `h2` "데모 고객으로 물어보세요.", "실제 개인정보는 입력하지 마세요."를 포함한 문구가 있다
     - `h1` "Local LLM — 은행 상담 AI"가 있다(`sr-only`여도 `getByRole("heading", { level: 1 })`로 찾힌다)
     - 칩 "잔액 얼마 남았어요?" 클릭 → `sendChat`이 1회, 인자는 `{session_id: 문자열, customer_id: "C001", message: "잔액 얼마 남았어요?"}`이고 `choice` 키가 없다
     - 같은 칩을 더블클릭(`user.dblClick`) → `sendChat` 1회
     - 입력창에 문구를 치고 Enter를 연달아 두 번 → `sendChat` 1회
     - 고객을 `C002`로 바꾸고 보낸 요청이 reject → 오류 말풍선 → "새 대화" 클릭 → log의 `textContent`가 안내 문구와 같고 칩이 다시 보인다 → 다음 요청은 `customer_id: "C002"`, `session_id`는 직전 요청과 다르다
     - 요청 중(끝나지 않은 promise)에는 "새 대화" 버튼이 비활성이다
2. `frontend/src/app/page.tsx` — `"use client"` 컴포넌트 하나. `sendChat` 호출은 이 파일 한 곳에 남긴다.
   - 초기화 함수 `reset(id: CustomerId)`로 고객 변경과 "새 대화"를 처리한다(ARCHITECTURE "상태 관리"). 이벤트 핸들러에서 부르고 useEffect로 하지 않는다.
   - 구조: `sr-only` `h1` → `<ScrollWorld />` → `<section id="chat">`(섹션 카피 + 챗 패널[상단: `CustomerPicker` + "새 대화" 버튼, 그 아래 `ChatWindow`]). 클래스와 문구는 UI_GUIDE "챗 섹션"·"챗 패널 상단"·"새 대화 버튼"과 PRD "챗 섹션"을 따른다.
   - "새 대화" 버튼은 `type="button"`이고 `pending`이면 비활성이다.
   - 연타 테스트(더블클릭·Enter 두 번)가 요청 2회로 실패하면 그때만 `send()`에 `useRef` 가드를 넣는다(ARCHITECTURE "연타"). 넣었으면 summary에 적는다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/app/page.test.tsx
grep -q 'id="chat"' src/app/page.tsx
grep -q 'z-\[45\]' src/app/page.tsx
test -z "$(grep -rlE 'teal-|stone-' src --include='*.tsx' --exclude='*.test.tsx' || true)"
test "$(grep -rl 'sendChat(' src --include='*.tsx' --exclude='*.test.tsx' | tr -d ' ')" = "src/app/page.tsx"
npm run lint
npx tsc --noEmit
npm run build
npm run test
test -z "$(grep -rlE 'localhost:8000|11434|/mock/|dangerouslySetInnerHTML' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 고객 변경과 "새 대화"가 같은 `reset`을 쓰고, useEffect로 초기화하지 않는가?
   - 챗 섹션이 `relative z-[45]` + 불투명 `bg-cream` + 위쪽 여백(`pt-24`)인가? (FE-009, UI_GUIDE "챗 섹션")
   - 기존 5개 케이스를 고치지 않았는가? (`git diff src/app/page.test.tsx`에 삭제된 줄은 `vi.mock` 추가와 무관한 줄이 없어야 한다)
   - `git status --short`에 `frontend/src/app/page*.tsx`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 연타 테스트가 통과하는데도 `send()`에 가드를 넣지 마라. 이유: 버튼 비활성과 칩이 사라지는 것으로 막는 것이 설계다. 불필요한 코드를 늘리지 않는다(ARCHITECTURE "연타").
- 초기화를 useEffect로 하지 마라. 이유: eslint-config-next의 react-hooks 규칙이 effect 안의 setState를 막아 `npm run lint`가 실패한다.
- 챗을 엔진 설정이나 엔진 DOM 안에 넣지 마라. 이유: 챗은 엔진 밖의 일반 섹션이다(FE-009).
- 요청 타임아웃·재시도·환경변수 목 분기를 넣지 마라. 이유: FE-005, FE-006.
- `src/components/`, `src/lib/`, `layout.tsx`, `globals.css`를 고치지 마라. 필요하면 `blocked`로 보고한다. 이유: 이전 step의 산출물과 테스트를 이 step에서 흔들지 않는다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
