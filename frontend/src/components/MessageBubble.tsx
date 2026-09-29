import { fillSlots } from "../lib/fillSlots";
import type { ChatMessage } from "../types/chat";

const BUBBLE = "w-fit max-w-[80%] rounded-lg px-4 py-3 text-sm leading-relaxed whitespace-pre-line animate-fade-in";

// 표시 전용 — 선택지는 ChatWindow가 말풍선 아래에 둔다.
export function MessageBubble(props: { message: ChatMessage }) {
  const { message } = props;

  if (message.role === "user") {
    return <div className={`${BUBBLE} ml-auto bg-stone-900 text-white`}>{message.text}</div>;
  }

  // 봇 말풍선만 슬롯을 치환한다. 고객이 친 {{...}}는 그대로 둔다.
  return (
    <div className={`${BUBBLE} bg-stone-100 ${message.error ? "text-red-700" : "text-stone-800"}`}>
      {fillSlots(message.text, message.slots ?? {}).map((part, i) =>
        part.slot ? (
          <span key={i} className="font-semibold tabular-nums">
            {part.text}
          </span>
        ) : (
          part.text
        ),
      )}
    </div>
  );
}
