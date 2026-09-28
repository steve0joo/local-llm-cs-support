# 아키텍처: 프론트엔드

## 디렉토리 구조
```
frontend/
├── next.config.ts             # rewrites: /api/:path* → http://localhost:8000/api/:path*
└── src/
    ├── app/
    │   ├── layout.tsx
    │   └── page.tsx           # 챗봇 페이지 (Client Component 하나로 시작)
    ├── components/
    │   ├── ChatWindow.tsx     # 대화 목록 + 입력창
    │   ├── MessageBubble.tsx  # 말풍선 (슬롯 치환된 텍스트 표시)
    │   ├── OptionButtons.tsx  # 선택지 버튼
    │   └── CustomerPicker.tsx # 데모 고객 선택
    ├── lib/
    │   ├── api.ts             # sendChat(req) — /api/chat 호출은 여기서만
    │   └── fillSlots.ts       # fillSlots(text, slots) — 순수 함수
    └── types/
        └── chat.ts            # ChatRequest, ChatResponse, ChatOption (계약 1과 동일)
```
테스트(Vitest + Testing Library, FE-004)는 대상 파일 옆에 `<이름>.test.ts(x)`로 둔다. 예: `src/lib/fillSlots.test.ts`, `src/components/OptionButtons.test.tsx`.
- 모듈은 named export로 내보낸다(`export function fillSlots`). 테스트는 대상을 상대경로로 import하고(`./fillSlots`), Vitest API는 `import { describe, it, expect } from "vitest"`로 명시해서 쓴다.

## TDD 착수점
- 첫 테스트: `src/lib/fillSlots.test.ts` — PRD 인수 기준의 세 경우(치환 성공, 누락 슬롯, 슬롯 없는 문장)를 아래 "fillSlots 규칙"대로 확인한다. 백엔드 없이 만들 수 있다.
- 이후 순서: `lib/api.ts`(`sendChat` 요청 형태, `fetch`는 목) → `OptionButtons`(클릭 시 `{message: label, choice}` 전송) → `MessageBubble` → `ChatWindow`·`page.tsx`.

## fillSlots 규칙
- `fillSlots(text: string, slots: Record<string, string>): SlotPart[]`, `type SlotPart = { text: string; slot: boolean }`. 둘 다 `lib/fillSlots.ts`에서 export한다.
- 문자열 대신 조각 배열을 돌려주는 이유: `MessageBubble`이 `slot: true` 조각에만 금액 스타일(`font-semibold tabular-nums`, UI_GUIDE)을 준다.
- 슬롯 토큰은 `{{`와 `}}` 사이의 이름이다(앞뒤 공백은 무시). 한 문장의 여러 슬롯, 같은 슬롯의 반복을 모두 치환한다.
- 토큰 경계마다 조각을 나눈다. 토큰 밖 글자는 `slot: false` 조각, 값이 있는 토큰은 그 값으로 된 `slot: true` 조각이다. 빈 문자열 조각은 만들지 않는다.
- `slots`에 키가 없으면 그 토큰 자리만 `"확인할 수 없습니다"`(`slot: false`)로 바꾼다(계약 1). 값이 빈 문자열이면 빈 조각이라 만들지 않는다. `text`에 없는 `slots` 키는 무시한다.
  - 예: `fillSlots("현재 잔액은 {{balance}}입니다.", {balance: "1,234,567원"})` → `[{text: "현재 잔액은 ", slot: false}, {text: "1,234,567원", slot: true}, {text: "입니다.", slot: false}]`
  - 예: `fillSlots("현재 잔액은 {{balance}}입니다.", {})` → `[{text: "현재 잔액은 ", slot: false}, {text: "확인할 수 없습니다", slot: false}, {text: "입니다.", slot: false}]`
- 슬롯이 없는 문장은 `[{text, slot: false}]` 하나를 돌려준다.
- 봇 말풍선만 `fillSlots`를 거친다. 고객 말풍선은 `text`를 그대로 보여준다. `slots`가 없는 메시지는 `{}`를 넘긴다.

## 패턴
- 페이지는 챗봇 하나다. 상호작용이 전부라서 `page.tsx`에서 Client Component 하나로 시작한다.
- 서버 컴포넌트, 데이터 페칭 라이브러리, 전역 상태 라이브러리는 쓰지 않는다.
- 백엔드 주소는 `next.config.ts` rewrites에만 둔다. 컴포넌트는 상대경로 `/api/chat`만 안다.

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
- `customerId: "C001" | "C002" | "C003"`
- `messages: {role: "user" | "bot", text: string, slots?: Record<string,string>, options?: ChatOption[]}[]`
- `pending: boolean` — 요청 중 입력·버튼 비활성화

## 핵심 규칙
- 슬롯 치환은 `fillSlots` 한 곳에서만 한다. 원본 `text`와 `slots`는 메시지에 그대로 저장하고, 렌더링할 때만 치환한다.
- 선택지는 가장 최근 봇 메시지의 것만 누를 수 있다. 이전 메시지의 선택지는 비활성화해 중복 요청을 막는다.
