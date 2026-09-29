# 아키텍처: 프론트엔드

## 디렉토리 구조
```
frontend/
├── package.json               # scripts: dev·build·start·lint(eslint)·test(vitest run --passWithNoTests). package-lock.json도 커밋
├── next.config.ts             # rewrites /api/:path* → http://localhost:8000/api/:path*, experimental.proxyTimeout, agentRules: false
├── vitest.config.ts           # jsdom 환경, setupFiles: src/test/setup.ts
├── eslint.config.mjs          # create-next-app 템플릿 그대로 (eslint-config-next)
└── src/
    ├── app/
    │   ├── layout.tsx         # <html lang="ko">, 메타데이터 제목
    │   ├── globals.css        # @import "tailwindcss" + fade-in 애니메이션
    │   ├── page.tsx           # 챗봇 페이지 (상태를 가진 Client Component 하나)
    │   └── page.test.tsx
    ├── components/
    │   ├── ChatWindow.tsx     # 대화 목록 + 첫 화면 안내 문구 + 입력 중 표시 + 입력창
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
- 페이지는 챗봇 하나다. 상호작용이 전부라서 `page.tsx`에서 Client Component 하나로 시작한다.
- 서버 컴포넌트, 데이터 페칭 라이브러리, 전역 상태 라이브러리는 쓰지 않는다.
- 백엔드 주소는 `next.config.ts` rewrites에만 둔다. 컴포넌트는 상대경로 `/api/chat`만 안다.
- 목(mock)은 테스트에만 둔다. 환경변수로 가짜 응답을 돌려주는 런타임 목 모드는 만들지 않는다(FE-005).
- 컴포넌트 역할: `page.tsx`가 상태와 `sendChat` 호출을 맡는다. `ChatWindow`는 props로 받은 `messages`·`pending`을 그리고 `onSend(text)`·`onSelect(option)`를 부른다. `MessageBubble`·`OptionButtons`·`CustomerPicker`는 props만 받는 표시 컴포넌트다.

## 데이터 흐름
```
입력 → ChatWindow.onSend → lib/api.sendChat({session_id, customer_id, message, choice?})
     → (rewrites) FastAPI /api/chat
     ← ChatResponse → messages 배열에 추가
     → MessageBubble: fillSlots(text, slots) 결과 표시 / OptionButtons: options 표시
선택지 클릭 → sendChat({message: option.label, choice: option.choice})
```

## 상태 관리 (`page.tsx`의 useState)
- `sessionId: string` — 최초 로드와 고객 변경 때 `crypto.randomUUID()`
- `customerId: CustomerId` — `"C001" | "C002" | "C003"`, 처음 값은 `"C001"`
- `messages: ChatMessage[]` — `ChatMessage = {role: "user" | "bot", text: string, slots?: Record<string,string>, options?: ChatOption[], error?: true}`. `error`는 요청이 실패했을 때 프론트가 추가하는 봇 메시지에만 붙는다.
- `pending: boolean` — 요청 중 입력·버튼·고객 선택 비활성화
- 고객 변경은 `CustomerPicker`의 onChange 핸들러에서 `customerId`·`sessionId`·`messages`(`[]`)를 한꺼번에 바꾼다. useEffect로 초기화하지 않는다(eslint-config-next의 react-hooks 규칙이 effect 안의 setState를 막는다).
- 입력창의 입력값은 `ChatWindow`의 로컬 상태다.

## 타입·API 규칙
- `types/chat.ts`는 계약 1을 그대로 옮긴다. `ChatRequest.choice?: string`(선택지를 누르지 않은 요청은 필드를 생략), `ChatResponse.type: "answer" | "clarify" | "unsupported"`, `agent: "balance" | "loan" | "interest" | null`, `topic: string | null`, `ChatOption = { label: string; choice: string }`. 계좌 선택 선택지의 `choice`도 에이전트 이름(`"balance"`)이다. 같은 파일의 `CustomerId`·`ChatMessage`는 화면용 타입이고 계약이 아니다.
- `sendChat(req: ChatRequest): Promise<ChatResponse>`는 `/api/chat`에 JSON으로 POST한다. 네트워크 오류나 2xx가 아닌 응답이면 throw하고, `page.tsx`가 잡아 오류 봇 메시지를 추가한다. 프론트는 요청 타임아웃과 재시도를 두지 않는다(FE-006).
- 봇 말풍선은 `type`과 관계없이 `text`(fillSlots)와 `options`를 보여준다. 미지원·상담원 안내 문구는 백엔드 `text`에 들어 있다.
- 선택지를 누르면 `label`을 고객 말풍선으로 추가한 뒤 요청을 보낸다. 요청 중(`pending`)에는 선택지도 비활성화한다.

## 화면 동작 규칙
- 첫 화면: `messages`가 비었으면 대화 영역 가운데에 안내 문구 "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요."를 보조 텍스트로 보여준다. 말풍선이 아니고 `messages`에 넣지 않는다. 고객을 바꿔 초기화했을 때도 같다.
- 전송: 입력값을 `trim()`한 값이 빈 문자열이면 전송 버튼을 비활성화하고 Enter도 무시한다. 전송하면 trim한 값을 고객 말풍선으로 추가해 보내고 입력창을 비운다.
- 요청 중(`pending`): 입력창·전송 버튼·모든 선택지·고객 선택을 비활성화하고, 봇 쪽에 입력 중 표시를 보여준다.
- 오류: `sendChat`이 throw하면 `{role: "bot", text: "잠시 후 다시 시도해 주세요", error: true}`를 추가한다.
- 줄바꿈: 말풍선 안의 `\n`(`text`와 `slots` 값 모두)은 줄바꿈으로 보인다(`whitespace-pre-line`). 여러 줄 슬롯 값도 다른 슬롯과 같은 금액 스타일을 받는다.
- 자동 스크롤: 메시지가 추가되거나 입력 중 표시가 바뀌면 대화 목록을 맨 아래로 내린다. 목록 컨테이너의 `scrollTop`을 `scrollHeight`로 바꾼다(jsdom에 없는 `scrollIntoView`는 쓰지 않는다).

## 핵심 규칙
- 슬롯 치환은 `fillSlots` 한 곳에서만 한다. 원본 `text`와 `slots`는 메시지에 그대로 저장하고, 렌더링할 때만 치환한다.
- 선택지는 가장 최근의 오류가 아닌 봇 메시지(`error`가 없는 봇 메시지 중 마지막)의 것만 누를 수 있다. 이전 메시지의 선택지는 비활성화해 중복 요청을 막는다. 오류 말풍선을 건너뛰는 이유는 선택지 요청이 실패했을 때 같은 선택지를 다시 눌러 재시도하게 하려는 것이다(FE-007).

## 통합 후 확인
실제 백엔드 응답을 브라우저에서 보는 확인이다. 런타임 목이 없으므로(FE-005) 아래 조건이 모두 갖춰진 뒤에 한다. 공통 `docs/ARCHITECTURE.md`의 "다음 라운드 체크리스트"(드라이런)와는 다른 목록이다.
- 조건: main에 gateway `/api/chat`, `cs-router`, 잔액조회 `handle()`과 `cs-balance` 모델이 준비됐고, main을 `feat-frontend`에 병합했다. 백엔드(8000)와 Ollama가 떠 있다. 브라우저는 `http://localhost:3000`으로 연다.
- [ ] `C001` 잔액 문의 → 금액이 `1,234,567원` 형식으로 굵게 보이고 `{{`가 남지 않는다(PRD 인수 기준)
- [ ] `C002` 잔액 문의 → 계좌 선택 되묻기와 계좌 버튼 2개 → 하나를 누르면 그 계좌 잔액이 보인다
- [ ] 거래내역 문의 → 여러 줄 거래내역이 줄마다 나뉘어 보인다
- [ ] 미지원 주제(예: 환전) → 미지원 안내와 상담원 연결 안내가 보인다
- [ ] 복합 문의(예: "대출 잔액이랑 이자 얼마 남았어요?") → 되묻기 선택지 → 누르면 그 에이전트의 답변이 온다(대출·이자 에이전트가 준비된 뒤)
- [ ] 백엔드를 켠 직후 첫 요청(모델 콜드 스타트)이 120초 안에 답을 받거나, 넘기면 오류 말풍선이 보인다
