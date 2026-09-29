import type { ChatOption } from "../types/chat";

// 표시 전용 — 요청은 page.tsx가 보낸다.
export function OptionButtons(props: {
  options: ChatOption[];
  disabled: boolean;
  onSelect: (option: ChatOption) => void;
}) {
  if (props.options.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {props.options.map((option, i) => (
        <button
          key={i}
          type="button"
          disabled={props.disabled}
          onClick={() => props.onSelect(option)}
          className="rounded-full border-[1.5px] border-accent-blue px-4 py-1.5 text-sm font-medium text-accent-blue hover:bg-accent-blue/10 disabled:opacity-40"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
