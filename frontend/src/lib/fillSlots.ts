export type SlotPart = { text: string; slot: boolean };

const SLOT_TOKEN = /\{\{([^{}]*)\}\}/g;
const MISSING = "확인할 수 없습니다";

// 슬롯 치환 규칙은 docs/frontend/ARCHITECTURE.md "fillSlots 규칙"을 따른다.
export function fillSlots(text: string, slots: Record<string, string>): SlotPart[] {
  const parts: SlotPart[] = [];
  let last = 0;

  for (const match of text.matchAll(SLOT_TOKEN)) {
    if (match.index > last) {
      parts.push({ text: text.slice(last, match.index), slot: false });
    }
    const name = match[1].trim();
    const value = name !== "" && Object.hasOwn(slots, name) ? slots[name] : "";
    parts.push(value === "" ? { text: MISSING, slot: false } : { text: value, slot: true });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push({ text: text.slice(last), slot: false });
  }
  return parts;
}
