# Step 4: message-bubble

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/PRD.md` (인수 기준 6 잔액 화면)
- `/docs/frontend/PRD.md` (사용자 스토리 2, 기능 범위)
- `/docs/frontend/ARCHITECTURE.md` (fillSlots 규칙의 마지막 항목, 화면 동작 규칙의 오류·줄바꿈, 핵심 규칙)
- `/docs/frontend/ADR.md` (FE-001)
- `/docs/frontend/UI_GUIDE.md` (말풍선, 오류 말풍선, 금액 슬롯 스타일, 애니메이션)
- step 1 산출물: `/frontend/src/lib/fillSlots.ts`
- step 0 산출물: `/frontend/src/types/chat.ts`

## 작업

수정 가능한 범위는 `frontend/src/components/`와 `phases/frontend/`뿐이다.

1. `frontend/src/components/MessageBubble.test.tsx` — **테스트를 먼저** 작성한다. 확인할 것:
   - 봇 메시지 `{text: "현재 잔액은 {{balance}}입니다.", slots: {balance: "1,234,567원"}}` → `1,234,567원`이 보이고, 그 글자를 감싼 요소에 `font-semibold`와 `tabular-nums` 클래스가 있으며, 말풍선 텍스트에 `{{`가 없다
   - 봇 메시지의 누락 슬롯 → `확인할 수 없습니다`가 보이고 금액 스타일이 붙지 않는다
   - `slots`가 없는 봇 메시지도 동작한다(`{}`로 치환)
   - 고객 메시지 `{role: "user", text: "{{balance}} 알려줘"}` → 글자 그대로 보인다(치환하지 않음)
   - `error: true`인 봇 메시지 → 말풍선에 오류 색 클래스(`text-red-700`)가 있다
   - `\n`이 든 텍스트·슬롯 값 → 말풍선에 `whitespace-pre-line` 클래스가 있고 `textContent`에 `\n`이 남아 있다
2. `frontend/src/components/MessageBubble.tsx`
   ```tsx
   export function MessageBubble(props: { message: ChatMessage });
   ```
   - 봇 메시지는 `fillSlots(message.text, message.slots ?? {})`의 조각을 그린다. `slot: true` 조각만 금액 스타일 `<span>`으로 감싼다.
   - 선택지(`options`)는 그리지 않는다. step 6의 `ChatWindow`가 말풍선 아래에 `OptionButtons`를 둔다.
   - 새 말풍선 fade-in(`animate-fade-in`)은 step 7에서 `globals.css`에 정의한다. 이 step에서 클래스를 붙여 둬도 된다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/MessageBubble.test.tsx
npx tsc --noEmit
npm run lint
test -z "$(grep -rl 'dangerouslySetInnerHTML' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 슬롯 치환을 `fillSlots` 밖(정규식 직접 사용, `replace`)에서 하지 않는가? (핵심 규칙: 치환은 한 곳에서만)
   - 원본 `text`·`slots`를 바꾸지 않고 렌더링할 때만 치환하는가?
   - `git status --short`에 `frontend/src/components/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `dangerouslySetInnerHTML`을 쓰지 마라. 이유: 백엔드 `text`와 슬롯 값을 HTML로 해석하면 안 된다. 줄바꿈은 `whitespace-pre-line`으로 처리한다.
- 고객 말풍선에 `fillSlots`를 적용하지 마라. 이유: 고객이 친 `{{...}}`가 슬롯으로 바뀌면 안 된다(ARCHITECTURE fillSlots 규칙).
- `frontend/src/components/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
