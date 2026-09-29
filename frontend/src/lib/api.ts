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
  const body = (await res.json()) as ChatResponse;
  // 렌더링을 깨뜨리는 두 가지만 확인한다(fillSlots의 text.matchAll, OptionButtons의 options.map).
  // 항목 안쪽 검증은 게이트웨이 응답 모델의 몫이고, 본문은 고치지 않고 그대로 돌려준다.
  if (typeof body.text !== "string" || (body.options != null && !Array.isArray(body.options))) {
    throw new Error("/api/chat 응답 형식 오류");
  }
  return body;
}
