import type { ChatRequest, ChatResponse } from "../types/chat";

// 백엔드 주소는 next.config.ts rewrites에만 둔다. 타임아웃·재시도는 두지 않는다(FE-006).
export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`/api/chat 요청 실패: ${res.status}`);
  }
  return (await res.json()) as ChatResponse;
}
