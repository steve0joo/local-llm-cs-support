# Step 14: chat-restyle

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/frontend/UI_GUIDE.md` ("색상", "말풍선", "선택지 버튼", "데모 고객 선택", 금지 사항)
- `/docs/frontend/ARCHITECTURE.md` (패턴의 컴포넌트 역할, 핵심 규칙)
- 이전 step 산출물: `/frontend/src/app/globals.css` (step 11의 색 토큰)
- `/frontend/src/components/MessageBubble.tsx`, `/frontend/src/components/OptionButtons.tsx`, `/frontend/src/components/CustomerPicker.tsx`와 각 `.test.tsx`

## 작업

표시 컴포넌트 세 개의 스타일만 UI_GUIDE로 바꾼다. 동작은 바꾸지 않는다. 수정 가능한 범위는 `frontend/src/components/MessageBubble.tsx`, `frontend/src/components/OptionButtons.tsx`, `frontend/src/components/CustomerPicker.tsx`, `phases/frontend/`뿐이다.

1. `MessageBubble.tsx` — UI_GUIDE "말풍선"의 클래스로 바꾼다(봇·고객·오류).
2. `OptionButtons.tsx` — UI_GUIDE "선택지 버튼"의 클래스로 바꾼다.
3. `CustomerPicker.tsx` — UI_GUIDE "데모 고객 선택"의 클래스로 바꾼다.

세 파일 모두 props, 마크업 구조, 문구, 접근성 이름(라벨)은 그대로 둔다. 기존 테스트가 확인하는 클래스 `text-red-700`, `font-semibold tabular-nums`, `whitespace-pre-line`과 `animate-fade-in`은 남긴다. 색은 step 11의 토큰 유틸리티(`bg-bubble`, `bg-ink`, `text-ink`, `text-ink-soft`, `border-accent-blue`, `text-accent-blue` 등)로 쓴다.

## Acceptance Criteria

```bash
cd frontend
test -z "$(grep -lE 'teal-|stone-' src/components/MessageBubble.tsx src/components/OptionButtons.tsx src/components/CustomerPicker.tsx || true)"
grep -q 'bg-bubble' src/components/MessageBubble.tsx
grep -q 'bg-ink' src/components/MessageBubble.tsx
grep -q 'text-red-700' src/components/MessageBubble.tsx
grep -q 'border-accent-blue' src/components/OptionButtons.tsx
grep -q 'rounded-full' src/components/OptionButtons.tsx
grep -q 'rounded-full' src/components/CustomerPicker.tsx
git diff --quiet -- src/components/MessageBubble.test.tsx src/components/OptionButtons.test.tsx src/components/CustomerPicker.test.tsx
npx vitest run src/components/MessageBubble.test.tsx src/components/OptionButtons.test.tsx src/components/CustomerPicker.test.tsx
npm run lint
npx tsc --noEmit
npm run build
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - UI_GUIDE 금지 사항(blur, 그라데이션 텍스트, 보라/인디고, 글로우, "Powered by AI")이 없는가?
   - 세 파일의 props·문구·라벨이 그대로인가? (`git diff`로 클래스 문자열만 바뀌었는지 본다)
   - `git status --short`에 위 세 파일과 `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 테스트 파일을 고치지 마라. 이유: 스타일만 바꾸는 step이다. 기존 테스트가 수정 없이 통과하는 것이 동작이 그대로라는 증거다. 테스트가 깨지면 구현을 되돌려 원인을 찾는다.
- props, 마크업 구조, 문구, 라벨을 바꾸지 마라. 이유: `ChatWindow`·`page.tsx`와 테스트가 그 구조에 기대고 있다.
- hex 값이나 arbitrary 색(`bg-[#…]`)을 컴포넌트에 직접 쓰지 마라. 이유: 색은 `globals.css`의 `@theme` 토큰 한 곳에서만 정한다(UI_GUIDE "색상").
- `ChatWindow.tsx`와 `page.tsx`를 고치지 마라. 이유: 각각 step 15, 16에서 테스트와 함께 바꾼다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
