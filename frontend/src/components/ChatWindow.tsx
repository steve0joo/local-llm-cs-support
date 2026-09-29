import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage, ChatOption } from "../types/chat";
import { MessageBubble } from "./MessageBubble";
import { OptionButtons } from "./OptionButtons";

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
    <div className="flex min-h-0 flex-1 flex-col bg-white">
      <div ref={listRef} role="log" className="flex-1 overflow-y-auto p-4">
        {props.messages.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-stone-500">
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
              <div className="w-fit rounded-lg bg-stone-100 px-4 py-3 text-sm text-stone-500">
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
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-stone-200 p-4">
        <input
          type="text"
          aria-label="메시지"
          value={input}
          disabled={props.pending}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 rounded-md border border-stone-300 px-4 py-3 text-sm focus:border-teal-700 focus:outline-none"
        />
        <button
          type="submit"
          disabled={props.pending || text === ""}
          className="rounded-md bg-teal-700 px-4 py-3 text-sm text-white hover:bg-teal-800 disabled:opacity-40"
        >
          전송
        </button>
      </form>
    </div>
  );
}
