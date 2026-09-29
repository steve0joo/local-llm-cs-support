# Step 7: chat-page

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (CRITICAL: 프론트엔드는 `/api/chat`만 호출)
- `/docs/PRD.md` (인수 기준 6 잔액 화면)
- `/docs/ARCHITECTURE.md` (계약 1 채팅 API, 계약 6 데모 고객 ID)
- `/docs/frontend/PRD.md` (사용자 스토리 전부, 인수 기준)
- `/docs/frontend/ARCHITECTURE.md` (데이터 흐름, 상태 관리, 타입·API 규칙, 화면 동작 규칙, 핵심 규칙)
- `/docs/frontend/ADR.md` (FE-002·003·005~007)
- `/docs/frontend/UI_GUIDE.md` (색상, 레이아웃, 타이포그래피, 애니메이션, 금지 사항)
- 이전 step 산출물: `/frontend/src/lib/api.ts`, `/frontend/src/components/` 전체, `/frontend/src/types/chat.ts`, `/frontend/src/app/layout.tsx`, `/frontend/src/app/globals.css`

## 작업

수정 가능한 범위는 `frontend/src/app/`와 `phases/frontend/`뿐이다.

1. `frontend/src/app/page.test.tsx` — **테스트를 먼저** 작성한다. `vi.mock("../lib/api", ...)`로 `sendChat`을 목으로 바꾼다(실제 `fetch` 금지). 확인할 것:
   - **잔액 화면(PRD 인수 기준)**: `sendChat`이 `{type: "answer", agent: "balance", topic: "balance", text: "현재 잔액은 {{balance}}입니다.", slots: {balance: "1,234,567원"}, options: []}`로 resolve → "잔액 알려줘" 전송 뒤 화면에 `1,234,567원`이 보이고 `document.body.textContent`에 `{{`가 없다. 첫 호출 인자는 `customer_id: "C001"`, `message: "잔액 알려줘"`, 문자열 `session_id`를 갖고 `choice` 키가 없다
   - **clarify 선택**: 첫 응답이 `type: "clarify"`, `options: [{label: "대출문의", choice: "loan"}, {label: "이자·연체", choice: "interest"}]` → "이자·연체"를 누르면 고객 말풍선 "이자·연체"가 추가되고, 두 번째 호출 인자가 `message: "이자·연체"`, `choice: "interest"`이며 `session_id`가 첫 호출과 같다
   - **오류**: `sendChat`이 reject → "잠시 후 다시 시도해 주세요"가 보이고, 입력창이 다시 활성이다
   - **요청 중**: `sendChat`이 아직 끝나지 않은 동안(직접 resolve하는 promise) 고객 선택·입력창이 비활성이고, resolve 뒤 다시 활성이다
   - **고객 변경**: 메시지를 하나 주고받은 뒤 고객을 `C002`로 바꾸면 말풍선이 모두 사라지고 첫 화면 안내 문구가 보인다. 다음 요청은 `customer_id: "C002"`이고 `session_id`가 이전과 다르다
2. `frontend/src/app/page.tsx` — `"use client"` 컴포넌트 하나. 상태와 흐름은 ARCHITECTURE "상태 관리"·"화면 동작 규칙"을 따른다.
   - `sessionId`는 `useState(() => crypto.randomUUID())`로 시작한다.
   - 전송: 고객 말풍선 추가 → `pending` 켜기 → `sendChat({session_id, customer_id, message, ...(choice ? { choice } : {})})` → 봇 말풍선(`text`·`slots`·`options`) 추가 또는 오류 말풍선 추가 → `pending` 끄기.
   - 선택지: `onSelect(option)` → `label`로 고객 말풍선을 추가하고 `choice`를 붙여 보낸다.
   - 고객 변경: `CustomerPicker`의 `onChange` 핸들러 안에서 `customerId`·`sessionId`(새 UUID)·`messages`(`[]`)를 바꾼다.
   - 상단(서비스 이름 "은행 상담" + `CustomerPicker`)과 `ChatWindow`를 UI_GUIDE 레이아웃대로 배치한다.
3. `frontend/src/app/globals.css` — `@import "tailwindcss";` 뒤에 `@theme`로 `--animate-fade-in`(0.2s)과 `@keyframes`를 정의한다. 페이지 배경 `#f5f5f4`.
4. `frontend/src/app/layout.tsx` — step 0의 `lang="ko"`·제목을 유지한다. 필요하면 body 클래스만 조정한다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/app/page.test.tsx
npm run lint
npx tsc --noEmit
npm run build
npm run test
test -z "$(grep -rlE 'localhost:8000|11434|/mock/' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `sendChat` 호출이 `page.tsx` 한 곳뿐인가? 상태 라이브러리·데이터 페칭 라이브러리를 쓰지 않았는가? (FE-002)
   - 고객 변경 초기화가 useEffect가 아니라 onChange 핸들러에 있는가?
   - UI_GUIDE의 금지 사항(blur, 그라데이션 텍스트, 보라/인디고, 글로우, "Powered by AI")이 없는가?
   - `git status --short`에 `frontend/src/app/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `sendChat`을 목으로 바꾸지 않은 테스트로 실제 네트워크를 부르지 마라. 이유: 백엔드가 없다(FE-005). 목은 테스트 파일 안에만 둔다.
- 환경변수로 가짜 응답을 돌려주는 분기나 요청 타임아웃을 넣지 마라. 이유: FE-005, FE-006.
- 고객 변경 초기화를 useEffect로 하지 마라. 이유: eslint-config-next의 react-hooks 규칙이 effect 안의 setState를 막아 `npm run lint`가 실패한다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 8(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `frontend/src/app/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 컴포넌트를 고쳐야 하면 `blocked`로 보고한다. 이유: 이전 step의 산출물과 테스트를 이 step에서 흔들지 않는다. 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
