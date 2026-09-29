# Step 3: option-buttons

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 1 — 선택지 클릭 시 요청 형태)
- `/docs/frontend/PRD.md` (사용자 스토리 3, 기능 범위의 선택지 버튼)
- `/docs/frontend/ARCHITECTURE.md` (패턴의 컴포넌트 역할, 핵심 규칙)
- `/docs/frontend/UI_GUIDE.md` (선택지 버튼 클래스, 간격 `gap-2`)
- step 0 산출물: `/frontend/src/types/chat.ts`, `/frontend/src/test/setup.ts`

## 작업

수정 가능한 범위는 `frontend/src/components/`와 `phases/frontend/`뿐이다.

1. `frontend/src/components/OptionButtons.test.tsx` — **테스트를 먼저** 작성한다(Testing Library + `@testing-library/user-event`). 확인할 것:
   - 선택지마다 `label` 텍스트의 버튼이 하나씩 보인다(`getByRole("button", { name })`)
   - 버튼을 누르면 `onSelect`가 그 선택지 객체(`{label, choice}`)로 한 번 불린다
   - `disabled`면 모든 버튼이 비활성이고, 눌러도 `onSelect`가 불리지 않는다
   - `options`가 빈 배열이면 버튼을 그리지 않는다
2. `frontend/src/components/OptionButtons.tsx`
   ```tsx
   export function OptionButtons(props: {
     options: ChatOption[];
     disabled: boolean;
     onSelect: (option: ChatOption) => void;
   });
   ```
   - 버튼은 `type="button"`이다. 스타일은 UI_GUIDE "선택지 버튼"을 따른다.
   - 요청을 직접 보내지 않는다. 고객 말풍선 추가와 `sendChat` 호출은 step 7의 `page.tsx`가 한다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/OptionButtons.test.tsx
npx tsc --noEmit
npm run lint
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 컴포넌트가 props만 받는 표시 컴포넌트이고 `lib/api`를 import하지 않는가?
   - UI_GUIDE의 금지 사항(보라/인디고, 글로우, blur, 그라데이션)이 없는가?
   - `git status --short`에 `frontend/src/components/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 이 컴포넌트에서 `sendChat`을 부르지 마라. 이유: 상태와 요청은 `page.tsx` 한 곳이 맡는다(ARCHITECTURE 패턴).
- `frontend/src/components/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
