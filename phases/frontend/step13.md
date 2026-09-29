# Step 13: scroll-world

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/frontend/PRD.md` ("랜딩" 표와 그 아래 상단바·04 CTA·힌트)
- `/docs/frontend/ARCHITECTURE.md` ("랜딩 엔진 통합" 전체, "에러 처리", "보안 규칙")
- `/docs/frontend/ADR.md` (FE-008, FE-009)
- `/frontend/public/scroll-world/scrub-engine.js` (파일 머리 주석의 USAGE와 `mountScrollWorld(container, config)`의 config 키. 읽기만 한다)
- 이전 step 산출물: `/frontend/src/app/globals.css`, `/frontend/src/app/layout.tsx`, `/frontend/eslint.config.mjs`

## 작업

엔진을 불러와 마운트하고, 실패하면 랜딩을 숨기는 컴포넌트를 만든다. 수정 가능한 범위는 `frontend/src/components/ScrollWorld.tsx`, `frontend/src/components/ScrollWorld.test.tsx`, `phases/frontend/`뿐이다.

1. `frontend/src/components/ScrollWorld.test.tsx` — **테스트를 먼저** 작성한다.
   - `vi.mock("next/script", …)`로 가짜 `Script`를 만든다. 가짜는 받은 props(`src`, `strategy`, `onReady`, `onError`)를 테스트가 꺼내 쓸 수 있게 저장하고, 실제 스크립트는 불러오지 않는다. `onReady`·`onError`는 테스트에서 `act()` 안에서 직접 부른다.
   - `window.mountScrollWorld`는 `vi.fn`으로 두고, 불리면 첫 인자(컨테이너)에 자식 요소 하나를 붙이게 한다. 실제 엔진처럼 컨테이너가 비지 않게 하려는 것이다. 테스트마다 `window.mountScrollWorld`를 지우고 `location.hash`를 비운다.
   - 컨테이너는 `screen.getByTestId("scroll-world")`로 찾는다.
   - 확인할 것:
     - Script props가 `src: "/scroll-world/scrub-engine.js"`, `strategy: "afterInteractive"`다
     - 처음 렌더: 컨테이너가 `min-h-dvh`이고 `hidden`이 아니다. `mountScrollWorld`는 아직 불리지 않았다
     - `onReady` → `mountScrollWorld`가 1회 불린다. 첫 인자는 컨테이너다. 둘째 인자인 설정은 다음과 같다: `sections`의 `id`가 순서대로 `backlog`·`finetune`·`onboard`·`privacy`, 모든 `still`이 `/scroll-world/`로 시작, 첫 섹션 `clip`이 `/scroll-world/vid/scene02.mp4`, `brand.name`이 `"Local LLM"`, `cta.href`가 `"#chat"`, 마지막 섹션 `cta.primary.href`가 `"#chat"`, `connectors`가 `[]`
     - `onReady`가 두 번 불려도(다시 마운트되는 경우) `mountScrollWorld`는 1회다
     - `onError` → 컨테이너가 `hidden`이고 `mountScrollWorld`는 불리지 않는다
     - `onReady`인데 `window.mountScrollWorld`가 없음 → `hidden`
     - `mountScrollWorld`가 throw → 예외가 테스트 밖으로 나오지 않고 `hidden`
     - `location.hash`가 `"#chat"`이고 문서에 `id="chat"` 요소가 있음(그 요소의 `scrollIntoView`는 `vi.fn`) → `onReady` 뒤 `scrollIntoView`가 1회 불린다. hash가 없으면 불리지 않는다
2. `frontend/src/components/ScrollWorld.tsx`
   ```tsx
   "use client";
   export function ScrollWorld(): React.JSX.Element
   ```
   - props가 없다. 컨테이너 `div`(`data-testid="scroll-world"`, ref)와 `next/script`의 `<Script>`를 그린다.
   - 로드·마운트 조건·실패 상태·hash·설정·타입은 ARCHITECTURE "랜딩 엔진 통합"을 그대로 따른다. 컨테이너 클래스는 실패면 `hidden`, 아니면 `min-h-dvh`다.
   - `LANDING` 설정 상수를 이 파일에 둔다. 값은 PRD "랜딩" 표(id·라벨·에셋·accent·scroll·eyebrow·제목·본문·태그)와 그 아래 목록(04 CTA, 상단바 브랜드·CTA, 힌트)을 옮긴다. 엔진 옵션은 ARCHITECTURE "설정" 항목을 따른다. 엔진 config 키 이름은 엔진 파일 머리 주석의 USAGE를 따른다(`brand`, `cta`, `hint`, `diveScroll`, `crossfade`, `sections[].{id,label,still,clip,accent,scroll,eyebrow,title,body,tags,cta}`, `connectors`).
   - `declare global`로 `Window.mountScrollWorld?` 타입을 이 파일에 둔다.

## Acceptance Criteria

```bash
cd frontend
npx vitest run src/components/ScrollWorld.test.tsx
npm run lint
npx tsc --noEmit
npm run build
npm run test
grep -q '"/scroll-world/scrub-engine.js"' src/components/ScrollWorld.tsx
test -z "$(grep -nE 'setInterval|setTimeout|dangerouslySetInnerHTML|beforeInteractive' src/components/ScrollWorld.tsx || true)"
test -z "$(grep -rlE 'localhost:8000|11434|/mock/' src || true)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 초기화가 `onReady`에 있고 전역 함수를 폴링하지 않는가?
   - 마운트 조건이 "컨테이너가 비었을 때"이고, 실패 세 경우(`onError`, 함수 없음, 예외)가 모두 `hidden`으로 가는가?
   - `LANDING`의 카피가 PRD 표와 글자 단위로 같은가? 설정에 정적 문자열만 있는가?
   - `git status --short`에 `frontend/src/components/ScrollWorld*.tsx`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `public/scroll-world/scrub-engine.js`를 고치지 마라. 이유: 원본과 같아야 한다(FE-008). 필요한 동작이 엔진에 없으면 `blocked`로 보고한다.
- `setInterval`·`setTimeout`으로 `window.mountScrollWorld`가 생겼는지 폴링하지 마라. 이유: 로드 완료 시점은 `onReady`가 알려준다(ARCHITECTURE "로드").
- `strategy="beforeInteractive"`를 쓰지 마라. 이유: 루트 layout에만 둘 수 있고 `onReady`·`onError`를 쓸 수 없다.
- 엔진 로드 재시도, 로딩 스피너, 실패 문구를 만들지 마라. 이유: 실패하면 랜딩을 숨겨 챗이 첫 화면이 되는 것이 설계다(PRD 제외, FE-009).
- 설정에 API 응답·사용자 입력·`dangerouslySetInnerHTML`을 쓰지 마라. 이유: 엔진이 설정을 innerHTML로 넣는다(ARCHITECTURE "보안 규칙").
- `page.tsx`에 `ScrollWorld`를 붙이지 마라. 이유: 페이지 조립은 step 16에서 페이지 테스트와 함께 한다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
