# Step 6: chat-window

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/frontend/PRD.md` (사용자 스토리 1·3, 기능 범위)
- `/docs/frontend/ARCHITECTURE.md` (패턴의 컴포넌트 역할, **화면 동작 규칙**, **핵심 규칙**의 선택지 활성 판정)
- `/docs/frontend/ADR.md` (FE-007)
- `/docs/frontend/UI_GUIDE.md` (레이아웃, 입력 필드·전송 버튼, 입력 중 표시, 첫 화면 안내 문구)
- step 3·4 산출물: `/frontend/src/components/OptionButtons.tsx`, `/frontend/src/components/MessageBubble.tsx`
- step 0 산출물: `/frontend/src/types/chat.ts`

## 작업

수정 가능한 범위는 `frontend/src/components/`와 `phases/frontend/`뿐이다.

1. `frontend/src/components/ChatWindow.test.tsx` — **테스트를 먼저** 작성한다(`@testing-library/user-event`). 확인할 것:
   - `messages`가 비었으면 첫 화면 안내 문구 "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요."가 보이고, 메시지가 있으면 보이지 않는다
   - 입력창에 `"  잔액 알려줘  "`를 치고 Enter → `onSend("잔액 알려줘")`가 한 번 불리고 입력창이 빈다. 전송 버튼 클릭도 같다
   - 공백만 입력하면 전송 버튼이 비활성이고, Enter를 눌러도 `onSend`가 불리지 않는다
   - `pending`이면 입력창·전송 버튼·모든 선택지 버튼이 비활성이고 입력 중 표시("답변 작성 중")가 보인다
   - 선택지가 있는 봇 메시지가 둘이면 마지막 것의 버튼만 활성이다
   - 선택지 있는 봇 메시지 뒤에 `error: true` 봇 메시지만 있으면 그 선택지는 활성이다(FE-007)
   - 선택지 있는 봇 메시지 뒤에 오류가 아닌 봇 메시지가 오면 그 선택지는 비활성이다
   - 활성 선택지를 누르면 `onSelect`가 그 선택지 객체로 불린다
2. `frontend/src/components/ChatWindow.tsx`
   ```tsx
   export function ChatWindow(props: {
     messages: ChatMessage[];
     pending: boolean;
     onSend: (text: string) => void;
     onSelect: (option: ChatOption) => void;
   });
   ```
   - 입력값은 이 컴포넌트의 로컬 상태다. 폼 제출(Enter)과 버튼 클릭이 같은 경로를 탄다.
   - 봇 메시지 아래에 `OptionButtons`를 둔다. 활성 판정은 "`error`가 없는 봇 메시지 중 마지막 것 && `!pending`"이다.
   - 자동 스크롤은 목록 컨테이너 ref의 `scrollTop`을 `scrollHeight`로 바꾸는 effect로 한다(메시지 수·`pending`이 바뀔 때). `scrollIntoView`는 쓰지 않는다(jsdom에 없다).
   - 입력 중 표시는 UI_GUIDE대로 봇 쪽 점 3개이고, 스크린리더용 텍스트 "답변 작성 중"을 갖는다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/ChatWindow.test.tsx
npx tsc --noEmit
npm run lint
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `ChatWindow`가 `sendChat`을 부르지 않고 `onSend`·`onSelect`만 부르는가?
   - effect 안에서 setState를 하지 않는가? (eslint-config-next의 react-hooks 규칙)
   - `git status --short`에 `frontend/src/components/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 선택지 활성 판정을 "배열의 마지막 메시지"로 하지 마라. 이유: 오류 말풍선 뒤에서도 직전 선택지를 다시 누를 수 있어야 한다(FE-007). 고객 말풍선이 마지막이어도 판정 대상은 봇 메시지다.
- `setupFiles`나 테스트에서 `Element.prototype.scrollIntoView`를 스텁해 구현을 통과시키지 마라. 이유: 자동 스크롤은 `scrollTop`으로 구현하기로 했다(ARCHITECTURE 화면 동작 규칙).
- `frontend/src/components/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
