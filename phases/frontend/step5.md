# Step 5: customer-picker

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 6 데모 고객 ID)
- `/docs/frontend/PRD.md` (사용자 스토리 5, 기능 범위의 데모 고객 선택)
- `/docs/frontend/ARCHITECTURE.md` (상태 관리의 고객 변경, 화면 동작 규칙의 요청 중)
- `/docs/frontend/ADR.md` (FE-003)
- `/docs/frontend/UI_GUIDE.md` (데모 고객 선택, 레이아웃 상단)
- step 0 산출물: `/frontend/src/types/chat.ts` (`CustomerId`, `CUSTOMER_IDS`)

## 작업

수정 가능한 범위는 `frontend/src/components/`와 `phases/frontend/`뿐이다.

1. `frontend/src/components/CustomerPicker.test.tsx` — **테스트를 먼저** 작성한다. 확인할 것:
   - "데모 고객" 라벨의 선택 상자(`getByLabelText` 또는 `getByRole("combobox")`)에 `C001`·`C002`·`C003` 세 항목이 이 순서로 있고, `value`가 선택돼 있다
   - `C002`를 고르면 `onChange("C002")`가 한 번 불린다
   - `disabled`면 선택 상자가 비활성이다
2. `frontend/src/components/CustomerPicker.tsx`
   ```tsx
   export function CustomerPicker(props: {
     value: CustomerId;
     disabled: boolean;
     onChange: (id: CustomerId) => void;
   });
   ```
   - 항목은 `CUSTOMER_IDS`로 그린다. 스타일은 UI_GUIDE "데모 고객 선택"을 따른다.
   - 초기화(`sessionId`·`messages`)는 하지 않는다. step 7의 `page.tsx`가 `onChange` 핸들러에서 한다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/CustomerPicker.test.tsx
npx tsc --noEmit
npm run lint
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 고객 ID 목록을 컴포넌트 안에 다시 적지 않고 `types/chat.ts`의 것을 쓰는가?
   - `git status --short`에 `frontend/src/components/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 데모 고객 목록에 `C001`~`C003` 밖의 ID를 넣지 마라. 이유: mock 데이터는 계약 6의 세 고객만 있다.
- `frontend/src/components/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
