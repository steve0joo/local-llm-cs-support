"use client";

import { useState } from "react";
import { ChatWindow } from "../components/ChatWindow";
import { CustomerPicker } from "../components/CustomerPicker";
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

  // 고객을 바꾸면 이 핸들러에서 대화를 초기화한다. useEffect로 하지 않는다.
  function handleCustomerChange(id: CustomerId) {
    setCustomerId(id);
    setSessionId(crypto.randomUUID());
    setMessages([]);
  }

  return (
    <main className="mx-auto flex h-dvh max-w-2xl flex-col">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <h1 className="text-base font-semibold text-stone-900">은행 상담</h1>
        <CustomerPicker value={customerId} disabled={pending} onChange={handleCustomerChange} />
      </header>
      <ChatWindow
        messages={messages}
        pending={pending}
        onSend={(text) => send(text)}
        onSelect={(option) => send(option.label, option.choice)}
      />
    </main>
  );
}
