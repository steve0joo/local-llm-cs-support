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
