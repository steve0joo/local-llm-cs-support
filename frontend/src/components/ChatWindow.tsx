import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage, ChatOption } from "../types/chat";
import { MessageBubble } from "./MessageBubble";
import { OptionButtons } from "./OptionButtons";

// 예시 질문 칩 — PRD "예시 질문 칩" 표 순서. 직접 입력과 같은 onSend로 보낸다(choice 없음).
const EXAMPLE_CHIPS = [
  "잔액 얼마 남았어요?",
  "대출 만기가 언제예요?",
  "연체 이자가 얼마예요?",
  "대출 잔액이랑 이자 얼마 남았어요?",
  "환전하고 싶어요",
];

// 요청은 page.tsx가 보낸다. 여기서는 onSend·onSelect만 부른다.
export function ChatWindow(props: {
  messages: ChatMessage[];
  pending: boolean;
  onSend: (text: string) => void;
  onSelect: (option: ChatOption) => void;
}) {
  const [input, setInput] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const text = input.trim();

  // 선택지는 오류가 아닌 봇 메시지 중 마지막 것만 누를 수 있다(FE-007).
  const activeIndex = props.messages.findLastIndex((m) => m.role === "bot" && !m.error);

  useEffect(() => {
    const list = listRef.current;
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }, [props.messages.length, props.pending]);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (text === "") {
      return;
    }
    props.onSend(text);
    setInput("");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={listRef} role="log" className="flex-1 overflow-y-auto overscroll-contain p-4">
        {props.messages.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-ink-soft">
            잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요.
          </p>
        ) : (
          <div className="space-y-3">
            {props.messages.map((message, i) => (
              <div key={i} className="space-y-2">
                <MessageBubble message={message} />
                {message.options && (
                  <OptionButtons
                    options={message.options}
                    disabled={props.pending || i !== activeIndex}
                    onSelect={props.onSelect}
                  />
                )}
              </div>
            ))}
            {props.pending && (
              <div className="w-fit rounded-[18px] rounded-bl-md bg-bubble px-4 py-3 text-sm text-ink-soft">
                <span aria-hidden="true" className="flex gap-1">
                  <span className="animate-pulse">•</span>
                  <span className="animate-pulse">•</span>
                  <span className="animate-pulse">•</span>
                </span>
                <span className="sr-only">답변 작성 중</span>
              </div>
            )}
          </div>
        )}
      </div>
      {props.messages.length === 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-2">
          {EXAMPLE_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              disabled={props.pending}
              onClick={() => props.onSend(chip)}
              className="rounded-full border border-accent-orange/30 bg-accent-orange/15 px-3.5 py-1.5 text-sm font-semibold text-ink hover:bg-accent-orange/25 disabled:opacity-40"
            >
              {chip}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-ink/10 p-4">
        <input
          type="text"
          aria-label="메시지"
          value={input}
          disabled={props.pending}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 rounded-full border border-ink/20 bg-white px-5 py-3 text-sm text-ink focus:border-accent-blue focus:outline-none disabled:opacity-40"
        />
        <button
          type="submit"
          disabled={props.pending || text === ""}
          className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-ink/90 disabled:opacity-40"
        >
          전송
        </button>
      </form>
    </div>
  );
}
