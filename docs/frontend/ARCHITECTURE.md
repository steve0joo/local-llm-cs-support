# 아키텍처: 프론트엔드

## 디렉토리 구조
```
frontend/
├── package.json               # scripts: dev·build·start·lint(eslint)·test(vitest run --passWithNoTests). package-lock.json도 커밋
├── next.config.ts             # rewrites /api/:path* → http://localhost:8000/api/:path*, experimental.proxyTimeout, agentRules: false
├── vitest.config.ts           # jsdom 환경, setupFiles: src/test/setup.ts
├── eslint.config.mjs          # create-next-app 템플릿 + globalIgnores에 "public/scroll-world/**"(엔진 원본은 lint하지 않는다)
├── public/
│   └── scroll-world/          # 웹사이트에서 복사한 원본. 수정 금지(FE-008)
│       ├── scrub-engine.js    # 스크롤 월드 엔진 (window.mountScrollWorld)
│       ├── scene02.webp       # 01 포스터 (= scene02.mp4 첫 프레임)
│       ├── finetune.webp      # 02
│       ├── reception.webp     # 03
│       ├── office.webp        # 04
│       └── vid/scene02.mp4    # 01 영상
└── src/
    ├── app/
    │   ├── layout.tsx         # <html lang="ko">, Pretendard CDN <link>, 메타데이터 제목
    │   ├── globals.css        # @import "tailwindcss" + @theme(색·폰트·fade-in) + 엔진 덮어쓰기(레이어 밖 CSS)
    │   ├── page.tsx           # 랜딩(ScrollWorld) + 챗 섹션. 상태를 가진 Client Component 하나
    │   └── page.test.tsx
    ├── components/
    │   ├── ScrollWorld.tsx    # 엔진 로드·마운트·실패 처리 + 랜딩 설정 상수(LANDING)
    │   ├── ChatWindow.tsx     # 대화 목록 + 첫 화면 안내 문구 + 예시 칩 + 입력 중 표시 + 입력창
    │   ├── MessageBubble.tsx  # 말풍선 (슬롯 치환된 텍스트 표시)
    │   ├── OptionButtons.tsx  # 선택지 버튼
    │   └── CustomerPicker.tsx # 데모 고객 선택
    ├── lib/
    │   ├── api.ts             # sendChat(req) — /api/chat 호출은 여기서만
    │   └── fillSlots.ts       # fillSlots(text, slots) — 순수 함수
    ├── test/
    │   └── setup.ts           # jest-dom 매처 + 테스트마다 cleanup
    └── types/
        └── chat.ts            # ChatRequest, ChatResponse, ChatOption (계약 1과 동일) + 화면 타입 CustomerId, ChatMessage
```
테스트(Vitest + Testing Library, FE-004)는 대상 파일 옆에 `<이름>.test.ts(x)`로 둔다. 예: `src/lib/fillSlots.test.ts`, `src/components/OptionButtons.test.tsx`, `src/app/page.test.tsx`.
- 모듈은 named export로 내보낸다(`export function fillSlots`). 테스트는 대상을 상대경로로 import하고(`./fillSlots`), Vitest API는 `import { describe, it, expect } from "vitest"`로 명시해서 쓴다. Next.js가 요구하는 `page.tsx`·`layout.tsx`의 default export는 예외다.
- `public/scroll-world/`의 원본 위치는 `~/Projects/local-llm-cs-support-website/`(git 저장소 아님)의 `scrub-engine.js`, `assets/*.webp`, `assets/vid/scene02.mp4`다. 원본 폴더는 수정하지 않는다.

## 스캐폴드·테스트 설정
- `create-next-app@16.3.6`의 `--empty` 템플릿으로 만든다. TypeScript strict, Tailwind CSS 4, ESLint, App Router, `src/` 디렉토리를 쓰고, import alias·React Compiler·`AGENTS.md`는 쓰지 않는다. 모든 import는 상대경로다.
- 버전은 메이저까지 고정하고, 정확한 버전은 `package-lock.json`이 정한다.
  - 앱: Next 16, React 19, Tailwind 4. TypeScript·ESLint는 템플릿 버전을 그대로 둔다.
  - 테스트: Vitest 5, vite 8, `@vitejs/plugin-react` 6, jsdom **29**, `@testing-library/react` 16, `@testing-library/dom` 10, `@testing-library/user-event` 14, `@testing-library/jest-dom` 7, `@types/node` 24.
  - jsdom 30은 Node 24.15 이상을 요구한다. 두 장비의 Node를 올리지 않으려고 29에 고정한다(Node 24.0 이상이면 된다).
  - `@types/node`는 템플릿 기본값(^20)이 Vitest 5의 peer 범위(^22 또는 >=24)에 맞지 않아서 24로 올린다.
- `npm run test`는 `vitest run --passWithNoTests`다. 테스트가 아직 없는 스캐폴드 단계에서도 `scripts/verify.sh`가 통과하게 하려는 것이다. `passWithNoTests`는 vitest 설정 파일에 넣지 않는다. 특정 테스트 파일을 지정한 실행(`npx vitest run <파일>`)은 그 파일이 없으면 실패해야 하기 때문이다.
- 테스트 설정 파일은 `src/test/setup.ts`다. `frontend/vitest.setup.ts`는 TDD 훅이 구현 파일로 보고 막는다. Vitest API를 명시적으로 import하므로(전역 API를 켜지 않음) RTL의 자동 cleanup이 돌지 않는다. 그래서 setup에서 `afterEach(cleanup)`을 건다.
- `next build`는 테스트 파일까지 타입 검사한다. `layout.tsx`는 전역 `LayoutProps` 대신 children 타입을 직접 적는다. 그래야 `npx tsc --noEmit`이 `next typegen` 없이 돈다.
- `next.config.ts`
  - `rewrites`: `/api/:path*` → `http://localhost:8000/api/:path*`
  - `experimental.proxyTimeout: 120_000`: rewrites 프록시의 기본 제한은 30초다. 모델 콜드 스타트를 기다리려고 120초로 늘린다(FE-006).
  - `agentRules: false`: Next 16의 `next dev`는 AI 에이전트 안에서 실행되면 `frontend/AGENTS.md`·`frontend/CLAUDE.md`를 만든다. 규칙은 루트 `CLAUDE.md`에 있으므로 끈다.

## TDD 착수점
- 첫 테스트: `src/lib/fillSlots.test.ts` — PRD 인수 기준의 세 경우(치환 성공, 누락 슬롯, 슬롯 없는 문장)를 아래 "fillSlots 규칙"대로 확인한다. 백엔드 없이 만들 수 있다.
- 이후 순서: `lib/api.ts`(`sendChat` 요청 형태, `fetch`는 목) → `OptionButtons`(클릭 시 선택한 option 전달) → `MessageBubble` → `CustomerPicker` → `ChatWindow` → `page.tsx`(`app/page.test.tsx`, `lib/api`는 `vi.mock`). TDD 훅은 `page.tsx`·`layout.tsx`를 막지 않지만 `page.tsx`도 테스트를 먼저 쓴다.
- 랜딩 통합 순서: 엔진·에셋 복사 → 테마 토큰(`globals.css`·`layout.tsx`) → `lib/api.ts` 응답 형식 확인 → `ScrollWorld`(`next/script`는 `vi.mock`, `window.mountScrollWorld`는 가짜 함수) → 표시 컴포넌트 스타일 교체 → `ChatWindow` 예시 칩 → `page.tsx` 조립·"새 대화"(`page.test.tsx`는 `ScrollWorld`도 `vi.mock`).

## fillSlots 규칙
- `fillSlots(text: string, slots: Record<string, string>): SlotPart[]`, `type SlotPart = { text: string; slot: boolean }`. 둘 다 `lib/fillSlots.ts`에서 export한다.
- 문자열 대신 조각 배열을 돌려주는 이유: `MessageBubble`이 `slot: true` 조각에만 금액 스타일(`font-semibold tabular-nums`, UI_GUIDE)을 준다.
- 슬롯 토큰은 정규식 `/\{\{([^{}]*)\}\}/g`에 맞는 구간이고, 이름은 캡처한 문자열에 `trim()`을 적용한 값이다. 한 문장의 여러 슬롯, 같은 슬롯의 반복을 모두 치환한다. 이 정규식에 맞지 않는 중괄호는 토큰이 아니라 일반 글자다.
- `slots` 값은 백엔드가 포맷을 끝낸 표시용 문자열이라(계약 1) 그대로 넣고 다시 치환하지 않는다.
- 계약 1의 "치환되지 않은 `{{...}}`"와 PRD의 "`{{`가 남지 않는다"는 `text` 안의 슬롯 토큰(위 정규식에 맞는 구간)을 말한다. 토큰이 아닌 중괄호와 `slots` 값 안의 글자는 그대로 보인다.
- 토큰 경계마다 조각을 나눈다. 토큰 밖 글자는 `slot: false` 조각, 값이 있는 토큰은 그 값으로 된 `slot: true` 조각이다. 인접한 `slot: false` 조각도 합치지 않고, 빈 문자열 조각은 만들지 않는다.
- `slots`에 그 이름의 키가 없거나(자기 속성 기준, `Object.hasOwn`) 값이 빈 문자열이면 "값이 없는" 슬롯이다(PRD 기능 범위). 그 토큰 자리만 `"확인할 수 없습니다"`(`slot: false`)로 바꾼다(계약 1). 이름이 빈 문자열인 토큰(`{{}}`, `{{ }}`)은 `slots`를 보지 않고 값이 없는 슬롯으로 본다. `text`에 없는 `slots` 키는 무시한다.
  - 예: `fillSlots("현재 잔액은 {{balance}}입니다.", {balance: "1,234,567원"})` → `[{text: "현재 잔액은 ", slot: false}, {text: "1,234,567원", slot: true}, {text: "입니다.", slot: false}]`
  - 예: `fillSlots("현재 잔액은 {{balance}}입니다.", {})` → `[{text: "현재 잔액은 ", slot: false}, {text: "확인할 수 없습니다", slot: false}, {text: "입니다.", slot: false}]`
- 슬롯이 없는 문장은 `[{text, slot: false}]` 하나를 돌려준다. `text`가 빈 문자열이면 `[]`다.
- 봇 말풍선만 `fillSlots`를 거친다. 고객 말풍선은 `text`를 그대로 보여준다. `slots`가 없는 메시지는 `{}`를 넘긴다.

## 패턴
- 페이지는 하나다. 위는 랜딩(`ScrollWorld`), 아래는 챗 섹션(`<section id="chat">`)이다. 상태는 `page.tsx`의 Client Component 하나가 가진다.
- 서버 컴포넌트, 데이터 페칭 라이브러리, 전역 상태 라이브러리는 쓰지 않는다.
- 백엔드 주소는 `next.config.ts` rewrites에만 둔다. 컴포넌트는 상대경로 `/api/chat`만 안다.
- 목(mock)은 테스트에만 둔다. 환경변수로 가짜 응답을 돌려주는 런타임 목 모드는 만들지 않는다(FE-005).
- 컴포넌트 역할: `page.tsx`가 상태와 `sendChat` 호출을 맡는다. `ChatWindow`는 props로 받은 `messages`·`pending`을 그리고 `onSend(text)`·`onSelect(option)`를 부른다. `MessageBubble`·`OptionButtons`·`CustomerPicker`는 props만 받는 표시 컴포넌트다. `ScrollWorld`는 props가 없고 챗 상태를 모른다.

## 랜딩 엔진 통합 (FE-008·FE-009)
- **로드**: `ScrollWorld`가 `next/script`(`src="/scroll-world/scrub-engine.js"`, `strategy="afterInteractive"`)로 엔진을 불러온다. 초기화는 `onReady`에서 한다. `onReady`는 스크립트 로드가 끝난 뒤, 그리고 컴포넌트가 다시 마운트될 때마다 불린다. 전역 함수가 생겼는지 폴링하지 않는다.
- **마운트 조건**: 컨테이너가 비어 있을 때만(`childElementCount === 0`) `window.mountScrollWorld(container, LANDING)`를 부른다. 이 조건은 같은 컨테이너에 엔진 DOM이 두 번 들어가는 것만 막는다. 엔진에는 정리 함수가 없다. 그래서 dev에서 컴포넌트가 새 컨테이너로 다시 마운트되면(Fast Refresh 등) 이전 인스턴스의 `window` 리스너(scroll·resize·orientationchange·load·pointerdown·touchstart)와 rAF 루프가 남는다. 개발 중에만 생기고 새로고침하면 사라진다. 프로덕션에서는 페이지가 하나라 한 번만 마운트된다.
- **상태**: 불러오는 중에는 컨테이너가 `min-h-dvh`다. 서버 HTML에는 엔진 트랙이 없어서, 이게 없으면 챗 섹션이 첫 화면에 잠깐 보인다. 마운트가 끝나면 엔진이 만든 트랙이 높이를 가진다. 실패하면 컨테이너를 숨긴다(`hidden`). 실패로 보는 경우는 세 가지다: `onError`, `onReady` 때 `window.mountScrollWorld`가 함수가 아님, `mountScrollWorld`가 예외를 던짐(try/catch). 실패하면 챗 섹션이 첫 화면이 된다. 재시도·로딩 표시·오류 문구는 없다.
- 마운트 예외를 잡는 이유: `onReady`는 effect 안에서 불린다. 예외가 올라가면 React 트리 전체가 내려가서 챗까지 흰 화면이 된다.
- **hash**: 마운트 직후 `location.hash === "#chat"`이면 `document.getElementById("chat")`를 `scrollIntoView()`한다. CTA를 누르면 URL이 `/#chat`이 된다. 그 상태로 새로고침하면 브라우저가 엔진 트랙이 생기기 전의 위치로 점프해서 랜딩 중간에 떨어진다.
- **설정**: `LANDING` 상수는 `ScrollWorld.tsx` 안에 둔다. 섹션의 id·라벨·에셋·accent·scroll·카피는 `docs/frontend/PRD.md` "랜딩" 표를 따르고, 상단바·04 CTA·힌트도 같은 절을 따른다. 에셋 경로는 `/scroll-world/...` 절대경로다. 엔진 옵션은 `diveScroll: 1.3`, `crossfade: 0.35`, `connectors: []`다(연결 클립이 없어서 디졸브를 넓게 둔다). 설정에는 정적 문자열만 넣는다. 엔진이 설정을 innerHTML로 넣기 때문이다(`esc()`로 이스케이프하지만 API 응답·사용자 입력은 넣지 않는다).
- **타입**: `ScrollWorld.tsx`에 `declare global { interface Window { mountScrollWorld?: (container: HTMLElement, config: object) => void } }`를 둔다.
- **CSS 레이어**: 엔진은 실행 중에 head에 `<style id="sw-css">@layer sw {…}</style>`를 넣는다. 이 레이어는 Tailwind 레이어(theme·base·components·utilities)보다 나중에 선언된다. 그래서 같은 명시도에서는 **엔진 CSS가 Tailwind 유틸리티를 이긴다**. 엔진이 만든 요소(`.sw-*`)와 `html, body`는 Tailwind 클래스로 덮어쓰지 말고 `globals.css`의 레이어 밖 CSS로 덮어쓴다. 레이어 밖 CSS는 모든 레이어를 이긴다. 덮어쓸 항목은 `docs/frontend/UI_GUIDE.md` "랜딩 (엔진)"에 있다.
- **겹침**: 엔진 레이어는 모두 `position: fixed`다. z-index는 배경 0, 장면 10, 카피 20, 힌트 30, 점 내비 40, 상단바 50, 진행 막대 60이다. 04 장면 카피는 끝까지 투명도 1로 남는다. 챗 섹션은 `relative z-[45]`와 불투명 크림 배경으로 장면·카피·점 내비를 덮고, 상단바(50)는 위에 남긴다. 상단바에는 배경이 없으므로 챗 섹션 위쪽에 상단바 높이만큼 여백을 둔다(UI_GUIDE).
- **앵커**: 상단바 CTA와 04 CTA는 엔진이 만든 `<a href="#chat">`다. Next 라우터를 거치지 않고 브라우저가 처리한다. 브랜드 링크 `#top`은 해당 id의 요소가 없어도 HTML 규칙상 문서 맨 위로 간다.

## 데이터 흐름
```
입력 → ChatWindow.onSend ─┐
예시 칩 → ChatWindow.onSend ┴→ lib/api.sendChat({session_id, customer_id, message})
선택지 클릭 → ChatWindow.onSelect → sendChat({session_id, customer_id, message: option.label, choice: option.choice})
     → (rewrites) FastAPI /api/chat
     ← ChatResponse → sendChat이 최소 형식 확인 → messages 배열에 추가
     → MessageBubble: fillSlots(text, slots) 결과 표시 / OptionButtons: options 표시
고객 변경 · 새 대화 → reset(customerId): 새 session_id, messages []
ScrollWorld: /scroll-world/scrub-engine.js · 에셋만 같은 origin에서 받는다(API 호출 없음)
```

## 상태 관리 (`page.tsx`의 useState)
- `sessionId: string` — 최초 로드와 초기화 때 `crypto.randomUUID()`
- `customerId: CustomerId` — `"C001" | "C002" | "C003"`, 처음 값은 `"C001"`
- `messages: ChatMessage[]` — `ChatMessage = {role: "user" | "bot", text: string, slots?: Record<string,string>, options?: ChatOption[], error?: true}`. `error`는 요청이 실패했을 때 프론트가 추가하는 봇 메시지에만 붙는다.
- `pending: boolean` — 요청 중 입력·버튼·칩·고객 선택·"새 대화" 비활성화
- 초기화는 함수 하나 `reset(id: CustomerId)`가 `customerId`·`sessionId`·`messages`(`[]`)를 한꺼번에 바꾼다. 고객 변경(`CustomerPicker`의 onChange)은 `reset(새 고객)`, "새 대화" 버튼은 `reset(현재 고객)`을 이벤트 핸들러에서 부른다. useEffect로 초기화하지 않는다(eslint-config-next의 react-hooks 규칙이 effect 안의 setState를 막는다).
- 입력창의 입력값은 `ChatWindow`의 로컬 상태다.
- `ScrollWorld`의 실패 여부는 `ScrollWorld` 안의 로컬 상태다.

## 타입·API 규칙
- `types/chat.ts`는 계약 1을 그대로 옮긴다. `ChatRequest.choice?: string`(선택지를 누르지 않은 요청은 필드를 생략), `ChatResponse.type: "answer" | "clarify" | "unsupported"`, `agent: "balance" | "loan" | "interest" | null`, `topic: string | null`, `ChatOption = { label: string; choice: string }`. 계좌 선택 선택지의 `choice`도 에이전트 이름(`"balance"`)이다. 같은 파일의 `CustomerId`·`ChatMessage`는 화면용 타입이고 계약이 아니다.
- `sendChat(req: ChatRequest): Promise<ChatResponse>`는 `/api/chat`에 JSON으로 POST한다. 네트워크 오류나 2xx가 아닌 응답이면 throw하고, `page.tsx`가 잡아 오류 봇 메시지를 추가한다. 프론트는 요청 타임아웃과 재시도를 두지 않는다(FE-006).
- **응답 최소 형식 확인**: `sendChat`은 2xx 본문을 파싱한 뒤, `text`가 문자열이 아니거나 `options`가 `undefined`·`null`이 아니면서 배열도 아니면 throw한다. 이 둘만 렌더링을 터뜨린다(`fillSlots`의 `text.matchAll`, `OptionButtons`의 `options.map`). `slots`는 `MessageBubble`의 `?? {}`로 이미 안전하다. 챗이 랜딩과 한 페이지에 있어서 렌더링 예외가 나면 페이지 전체가 흰 화면이 된다. 항목 안쪽(선택지의 `label` 타입, 슬롯 값 타입)은 확인하지 않는다. 그건 게이트웨이의 응답 모델이 할 일이다.
- 봇 말풍선은 `type`과 관계없이 `text`(fillSlots)와 `options`를 보여준다. 미지원·상담원 안내 문구는 백엔드 `text`에 들어 있다.
- 선택지를 누르면 `label`을 고객 말풍선으로 추가한 뒤 요청을 보낸다. 요청 중(`pending`)에는 선택지도 비활성화한다.

## 화면 동작 규칙
- 첫 화면: `messages`가 비었으면 대화 영역 가운데에 안내 문구 "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요."를 보조 텍스트로 보여준다. 말풍선이 아니고 `messages`에 넣지 않는다. 고객 변경이나 "새 대화"로 초기화했을 때도 같다.
- 예시 칩: `messages`가 비었을 때만, 대화 목록(`role="log"`) **밖**의 입력창 바로 위에 보인다. 목록 밖에 두는 이유는 두 가지다. 칩은 대화 내용이 아니라 조작 버튼이고, 기존 테스트가 빈 목록의 텍스트를 안내 문구와 정확히 비교한다. 누르면 `onSend(칩 문구)`를 부른다. 직접 입력과 같은 경로라서 `choice` 키가 없다. `pending`이면 비활성이다. 칩 문구는 `ChatWindow.tsx`의 상수이고 PRD "예시 질문 칩" 표를 따른다.
- 전송: 입력값을 `trim()`한 값이 빈 문자열이면 전송 버튼을 비활성화하고 Enter도 무시한다. 전송하면 trim한 값을 고객 말풍선으로 추가해 보내고 입력창을 비운다.
- 요청 중(`pending`): 입력창·전송 버튼·모든 선택지·예시 칩·고객 선택·"새 대화"를 비활성화하고, 봇 쪽에 입력 중 표시를 보여준다.
- 연타: 요청 중 비활성화와 칩이 사라지는 것으로 막는다. React는 클릭·키 입력 같은 이산 이벤트 직후 화면을 바로 갱신하므로, 두 번째 이벤트는 비활성 버튼이나 사라진 칩에 닿는다. `send()` 안에 별도 가드는 두지 않는다. 대신 테스트(칩 더블클릭·Enter 연타 → 요청 1번)로 확인한다. 테스트가 실패하면 그때 ref 가드를 넣는다.
- 오류: `sendChat`이 throw하면 `{role: "bot", text: "잠시 후 다시 시도해 주세요", error: true}`를 추가한다. 다시 시작하는 경로는 세 가지다: 선택지 재시도(FE-007), 직접 입력, "새 대화".
- 새 대화: 챗 패널 상단의 데모 고객 선택 옆 버튼이다. 누르면 `reset(현재 customerId)` — 대화가 비고, 안내 문구와 칩이 다시 보이고, 다음 요청은 새 `session_id`로 나간다.
- 줄바꿈: 말풍선 안의 `\n`(`text`와 `slots` 값 모두)은 줄바꿈으로 보인다(`whitespace-pre-line`). 여러 줄 슬롯 값도 다른 슬롯과 같은 금액 스타일을 받는다.
- 자동 스크롤: 메시지가 추가되거나 입력 중 표시가 바뀌면 대화 목록을 맨 아래로 내린다. 목록 컨테이너의 `scrollTop`을 `scrollHeight`로 바꾼다(jsdom에 없는 `scrollIntoView`는 쓰지 않는다).
- 스크롤 연결: 대화 목록에 `overscroll-contain`을 준다. 목록 끝에서 스크롤이 페이지로 넘어가 랜딩이 되감기지 않게 한다.

## 에러 처리
| 실패 | 화면 | 처리 위치 |
|------|------|----------|
| `/api/chat` 네트워크 오류, 2xx가 아닌 응답, JSON 파싱 실패 | 오류 말풍선 | `sendChat` throw → `page.tsx` catch |
| 응답 형식 위반(`text`가 문자열 아님, `options`가 배열 아님) | 오류 말풍선 | `sendChat` throw ("타입·API 규칙") |
| 백엔드 무응답 | 입력 중 표시, 최대 120초 뒤 오류 말풍선 | rewrites `proxyTimeout`(FE-006) |
| 엔진 JS 로드 실패, 함수 없음, 마운트 예외 | 랜딩 없이 챗 섹션이 첫 화면 | `ScrollWorld` 실패 상태 |
| 영상 로드 실패 | 스틸 이미지 유지 | 엔진 내장 |
| 폰트 CDN 실패 | 시스템 폰트 | font-family fallback |

## 보안 규칙
- 엔진 설정에는 정적 문자열만 넣는다. `src/`에서 `dangerouslySetInnerHTML`을 쓰지 않는다. 챗의 봇·고객 텍스트는 React 텍스트 노드로만 그린다.
- 외부 리소스는 Pretendard CSS 하나(jsdelivr, 버전 `1.3.9` 고정)다. JS를 CDN에서 받지 않는다. 엔진은 같은 origin의 `public/` 파일이다.
- 엔진은 같은 origin의 정적 영상·이미지만 fetch한다. API 호출은 `sendChat` 한 곳이다(CLAUDE.md CRITICAL: 프론트엔드는 `/api/chat`만 호출).
- 카피와 칩 문구는 직접 쓴다. AI Hub 데이터 원문을 인용하지 않고 은행 이름을 쓰지 않는다.
- 챗 섹션 본문에 "실제 개인정보는 입력하지 마세요."를 둔다(PRD). 입력된 개인정보의 마스킹은 백엔드 계약(계약 4)대로 한다.
- 시연은 아래 "시연 방식"대로 발표자 PC의 localhost에서만 한다.

## 핵심 규칙
- 슬롯 치환은 `fillSlots` 한 곳에서만 한다. 원본 `text`와 `slots`는 메시지에 그대로 저장하고, 렌더링할 때만 치환한다.
- 선택지는 가장 최근의 오류가 아닌 봇 메시지(`error`가 없는 봇 메시지 중 마지막)의 것만 누를 수 있다. 이전 메시지의 선택지는 비활성화해 중복 요청을 막는다. 오류 말풍선을 건너뛰는 이유는 선택지 요청이 실패했을 때 같은 선택지를 다시 눌러 재시도하게 하려는 것이다(FE-007).
- `public/scroll-world/`의 파일은 원본과 바이트 단위로 같아야 한다(FE-008).

## 시연 방식
- 발표자 PC의 브라우저에서 `http://localhost:3000`으로만 조작한다. 방문자 기기 접속은 범위 밖이다(PRD 제외).
- `next dev`와 `next start`는 기본으로 `0.0.0.0`에 열린다. 그래서 같은 네트워크의 누구나 프록시를 거쳐 `/api/chat`(모델)을 부를 수 있다. 발표 때는 `-H 127.0.0.1`을 붙인다. `package.json` 스크립트는 바꾸지 않는다(팀원 개발 편의).
- 시연은 프로덕션 빌드로 한다: `cd frontend && npm run build && npm run start -- -H 127.0.0.1`. dev의 StrictMode 이중 effect와 Fast Refresh 영향을 배제하기 위해서다.
- LAN 주소(http)로 열면 보안 컨텍스트가 아니어서 `crypto.randomUUID`가 없고 챗이 깨진다. 방문자 기기 접속이 필요해지면 HTTPS와 접근 제어를 따로 정한다.

## 통합 후 확인
실제 백엔드 응답을 브라우저에서 보는 확인이다. 런타임 목이 없으므로(FE-005) 아래 조건이 모두 갖춰진 뒤에 한다. 공통 `docs/ARCHITECTURE.md`의 "다음 라운드 체크리스트"(드라이런)와는 다른 목록이다.
- 조건: main에 gateway `/api/chat`, `cs-router`, 잔액조회 `handle()`과 `cs-balance` 모델이 준비됐고, main을 `feat-frontend`에 병합했다. 백엔드(8000)와 Ollama가 떠 있다. 브라우저는 `http://localhost:3000`으로 연다.
- [ ] `C001` 잔액 문의 → 금액이 `1,234,567원` 형식으로 굵게 보이고 `{{`가 남지 않는다(PRD 인수 기준)
- [ ] `C002` 잔액 문의 → 계좌 선택 되묻기와 계좌 버튼 2개 → 하나를 누르면 그 계좌 잔액이 보인다
- [ ] 거래내역 문의 → 여러 줄 거래내역이 줄마다 나뉘어 보인다
- [ ] 미지원 주제(예: 환전) → 미지원 안내와 상담원 연결 안내가 보인다
- [ ] 복합 문의(예: "대출 잔액이랑 이자 얼마 남았어요?") → 되묻기 선택지 → 누르면 그 에이전트의 답변이 온다(대출·이자 에이전트가 준비된 뒤)
- [ ] 백엔드를 켠 직후 첫 요청(모델 콜드 스타트)이 120초 안에 답을 받거나, 넘기면 오류 말풍선이 보인다

### 발표 전 체크리스트
- [ ] "시연 방식"대로 프로덕션 빌드를 `127.0.0.1`로 띄운다
- [ ] 모델 워밍업: 에이전트마다 한 번씩 요청해 콜드 스타트를 미리 치른다(FE-006의 120초를 발표 중에 겪지 않게)
- [ ] 예시 칩을 하나씩 눌러 본다. "준비 중인 기능입니다."로 답하는 칩은 `ChatWindow.tsx`의 칩 상수와 PRD "예시 질문 칩" 표에서 뺀다
- [ ] 04 장면 카피(마스킹·슬롯)를 `docs/PRD.md` 인수 기준 5·6 결과와 대조한다. 통과하지 않았으면 PRD "랜딩" 표와 `LANDING` 상수의 문구를 함께 고친다
