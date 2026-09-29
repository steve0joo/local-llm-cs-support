# Step 1: fill-slots

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 1 — "치환되지 않은 `{{...}}`" 문장, 계약 4 슬롯 형식)
- `/docs/frontend/PRD.md` (기능 범위의 슬롯 치환, 인수 기준)
- `/docs/frontend/ARCHITECTURE.md` (**fillSlots 규칙** — 이 step의 기준 전부, TDD 착수점)
- `/docs/frontend/ADR.md` (FE-001)
- step 0 산출물: `/frontend/package.json`, `/frontend/vitest.config.ts`, `/frontend/src/test/setup.ts`, `/frontend/src/types/chat.ts`

## 작업

수정 가능한 범위는 `frontend/src/lib/`와 `phases/frontend/`뿐이다.

1. `frontend/src/lib/fillSlots.test.ts` — **테스트를 먼저** 작성한다(TDD 가드가 강제한다). "fillSlots 규칙"의 각 문장을 깨는 입력을 재현한다. 최소한 다음을 넣는다.
   - 문서의 두 예시(치환 성공, 누락 슬롯)와 슬롯 없는 문장, 빈 문자열 → `[]`
   - 한 문장의 여러 슬롯, 같은 슬롯의 반복
   - 이름 앞뒤 공백(`{{ balance }}`) → `balance`로 치환
   - 빈 이름(`{{}}`, `{{ }}`)과 빈 문자열 값(`{balance: ""}`) → `"확인할 수 없습니다"`(`slot: false`)
   - 상속 속성 이름(`{{toString}}`, `{{constructor}}`)을 `{}`로 → `"확인할 수 없습니다"` (`Object.hasOwn` 기준)
   - 재치환 금지: 슬롯 값 안의 `{{x}}`는 그대로 `slot: true` 조각의 글자로 남는다
   - 토큰이 아닌 중괄호(`{a}`, 짝이 맞지 않는 `{{a`)는 일반 글자로 남는다
   - 문장이 토큰으로 시작·끝나거나 토큰이 붙어 있을 때(`{{a}}{{b}}`) 빈 조각이 없고, 인접한 `slot: false` 조각을 합치지 않는다
   - `\n`이 든 `text`와 슬롯 값은 글자 그대로 조각에 남는다
2. `frontend/src/lib/fillSlots.ts`
   ```ts
   export type SlotPart = { text: string; slot: boolean };
   export function fillSlots(text: string, slots: Record<string, string>): SlotPart[];
   ```
   - 순수 함수다. `slots` 인자를 바꾸지 않는다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/lib/fillSlots.test.ts
npx tsc --noEmit
npm run lint
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 테스트가 "fillSlots 규칙"의 문장마다 그 규칙을 깨는 입력을 갖고 있는가? (스모크 테스트만 있으면 부족)
   - 반환 타입이 문자열이 아니라 `SlotPart[]`인가?
   - `git status --short`에 `frontend/src/lib/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 문서의 두 예시 기대값을 바꾸지 마라. 이유: 공통 계약 1과 PRD 인수 기준이 이 결과에 기대고 있다. 문서와 다르게 구현해야 한다고 판단되면 `blocked`로 보고한다.
- `in` 연산자나 `slots[name] !== undefined`로 키 존재를 판정하지 마라. 이유: `toString` 같은 상속 속성이 값으로 잡힌다(`Object.hasOwn` 기준).
- `frontend/src/lib/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(`docs/`, `backend/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
