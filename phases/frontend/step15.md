# Step 15: chat-window

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/frontend/PRD.md` ("챗 섹션", "예시 질문 칩" 표)
- `/docs/frontend/ARCHITECTURE.md` ("화면 동작 규칙"의 예시 칩·요청 중·연타·스크롤 연결, 패턴의 컴포넌트 역할)
- `/docs/frontend/UI_GUIDE.md` ("예시 칩", "입력 중 표시", "첫 화면 안내 문구", "입력 필드 / 전송 버튼", 레이아웃의 대화 목록)
- 이전 step 산출물: `/frontend/src/app/globals.css`(색 토큰), step 14에서 바꾼 `/frontend/src/components/MessageBubble.tsx`·`OptionButtons.tsx`
- `/frontend/src/components/ChatWindow.tsx`, `/frontend/src/components/ChatWindow.test.tsx`

## 작업

`ChatWindow`에 예시 칩을 넣고, 스크롤 연결을 막고, 스타일을 UI_GUIDE로 바꾼다. 수정 가능한 범위는 `frontend/src/components/ChatWindow.tsx`, `frontend/src/components/ChatWindow.test.tsx`, `phases/frontend/`뿐이다.

1. `frontend/src/components/ChatWindow.test.tsx` — 기존 케이스는 고치지 않고 **테스트를 먼저** 추가한다.
   - `messages: []` → PRD "예시 질문 칩" 표의 문구 5개가 각각 버튼으로 보인다. 모든 칩 버튼이 `role="log"` 요소 **밖**에 있고, log의 `textContent`는 안내 문구와 정확히 같다
   - `messages`가 1개 이상 → 칩 버튼이 없다
   - 칩 클릭 → `onSend`가 그 칩 문구로 1회 불리고 `onSelect`는 불리지 않는다
   - `pending: true`, `messages: []` → 칩이 모두 비활성이고, 눌러도 `onSend`가 불리지 않는다
   - 대화 목록(`role="log"`)에 `overscroll-contain` 클래스가 있다
2. `frontend/src/components/ChatWindow.tsx`
   - props는 그대로 둔다(`messages`, `pending`, `onSend`, `onSelect`). 칩은 새 prop 없이 `onSend`를 부른다.
   - 칩 문구 상수를 이 파일에 둔다(PRD 표 순서). 위치·표시 조건·비활성 조건은 ARCHITECTURE "화면 동작 규칙"의 예시 칩을 따른다.
   - 대화 목록, 안내 문구, 입력 중 표시, 입력 폼, 칩의 클래스를 UI_GUIDE로 바꾼다. 선택지 활성 판정(FE-007), 자동 스크롤, 입력 처리 로직은 그대로 둔다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/ChatWindow.test.tsx
test -z "$(grep -nE 'teal-|stone-' src/components/ChatWindow.tsx || true)"
grep -q 'overscroll-contain' src/components/ChatWindow.tsx
grep -q '환전하고 싶어요' src/components/ChatWindow.tsx
npm run lint
npx tsc --noEmit
npm run build
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `ChatWindow`가 여전히 `sendChat`을 부르지 않고 props 콜백만 부르는가?
   - 칩이 log 밖, 입력창 바로 위에 있고 빈 대화에서만 보이는가?
   - 기존 테스트 케이스를 고치지 않았는가? (`git diff src/components/ChatWindow.test.tsx`에 삭제된 줄이 없어야 한다)
   - `git status --short`에 `frontend/src/components/ChatWindow*.tsx`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 칩을 `role="log"` 안에 넣지 마라. 이유: 칩은 대화 내용이 아니고, `page.test.tsx`가 초기화 뒤 log의 텍스트를 안내 문구와 정확히 비교한다(ARCHITECTURE "화면 동작 규칙").
- 칩용 새 prop(예: `onExample`)이나 별도 컴포넌트 파일을 만들지 마라. 이유: 칩은 직접 입력과 같은 경로(`onSend`)라 `choice`가 없어야 하고, 한 번만 쓰는 코드라 파일을 나누지 않는다.
- 대화 중에 칩을 다시 보여주거나 고객별로 다른 칩을 만들지 마라. 이유: PRD 제외 범위다. 다시 시작은 "새 대화"로 한다(step 16).
- `scrollIntoView`를 쓰지 마라. 이유: jsdom에 없고, 페이지 전체를 움직인다. 자동 스크롤은 목록의 `scrollTop`만 바꾼다.
- `page.tsx`를 고치지 마라. 이유: 페이지 조립은 step 16에서 한다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
