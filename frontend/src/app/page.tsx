"use client";

import { useState } from "react";
import { ChatWindow } from "../components/ChatWindow";
import { CustomerPicker } from "../components/CustomerPicker";
import { ScrollWorld } from "../components/ScrollWorld";
import { sendChat } from "../lib/api";
import type { ChatMessage, CustomerId } from "../types/chat";

export default function Home() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [customerId, setCustomerId] = useState<CustomerId>("C001");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);

  async function send(message: string, choice?: string) {
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setPending(true);
    try {
      const res = await sendChat({
        session_id: sessionId,
        customer_id: customerId,
        message,
        ...(choice ? { choice } : {}),
      });
      setMessages((prev) => [...prev, { role: "bot", text: res.text, slots: res.slots, options: res.options }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "잠시 후 다시 시도해 주세요", error: true }]);
    } finally {
      setPending(false);
    }
  }

  // 고객 변경과 "새 대화"는 이벤트 핸들러에서 이 함수로 초기화한다. useEffect로 하지 않는다.
  function reset(id: CustomerId) {
    setCustomerId(id);
    setSessionId(crypto.randomUUID());
    setMessages([]);
  }

  return (
    <main>
      <h1 className="sr-only">Local LLM — 은행 상담 AI</h1>
      <ScrollWorld />
      {/* z-[45]: 엔진 장면·카피·점 내비를 덮고 상단바(50) 아래. pt-24: 배경 없는 상단바 높이만큼 여백 (FE-009) */}
      <section id="chat" className="relative z-[45] min-h-dvh bg-cream px-[clamp(18px,5vw,64px)] pt-24 pb-10">
        <div className="grid gap-10 lg:grid-cols-[1fr_minmax(0,40rem)] lg:items-center">
          <div>
            <p className="text-[0.8rem] font-bold tracking-[.16em] text-accent-blue">직접 체험</p>
            <h2 className="mt-3 text-[clamp(2rem,4.4vw,3.5rem)] leading-tight font-bold break-keep text-ink">
              데모 고객으로 물어보세요.
            </h2>
            <p className="mt-4 break-keep text-ink-soft">가상 고객 데이터입니다. 실제 개인정보는 입력하지 마세요.</p>
          </div>
          <div className="flex h-[min(44rem,calc(100dvh_-_8rem))] w-full max-w-[40rem] flex-col overflow-hidden rounded-[20px] border border-ink/12 bg-surface">
            <div className="flex items-center justify-between gap-2 border-b border-ink/10 px-4 py-3">
              <CustomerPicker value={customerId} disabled={pending} onChange={reset} />
              <button
                type="button"
                disabled={pending}
                onClick={() => reset(customerId)}
                className="rounded-full border-[1.5px] border-ink/25 px-3.5 py-1.5 text-sm font-medium text-ink hover:bg-ink/5 disabled:opacity-40"
              >
                새 대화
              </button>
            </div>
            <ChatWindow
              messages={messages}
              pending={pending}
              onSend={(text) => send(text)}
              onSelect={(option) => send(option.label, option.choice)}
            />
          </div>
        </div>
      </section>
    </main>
  );
}
