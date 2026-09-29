import { useId } from "react";
import { CUSTOMER_IDS, type CustomerId } from "../types/chat";

// 표시 전용 — 대화 초기화(sessionId·messages)는 page.tsx의 onChange 핸들러가 한다.
export function CustomerPicker(props: {
  value: CustomerId;
  disabled: boolean;
  onChange: (id: CustomerId) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm text-stone-500">
        데모 고객
      </label>
      <select
        id={id}
        value={props.value}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.value as CustomerId)}
        className="rounded-md border border-stone-300 px-3 py-1.5 text-sm text-stone-700 focus:border-teal-700 focus:outline-none disabled:opacity-40"
      >
        {CUSTOMER_IDS.map((customerId) => (
          <option key={customerId} value={customerId}>
            {customerId}
          </option>
        ))}
      </select>
    </div>
  );
}
