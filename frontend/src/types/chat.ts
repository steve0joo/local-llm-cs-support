// 계약 1 — POST /api/chat (docs/ARCHITECTURE.md)
export type ChatOption = { label: string; choice: string };

export type ChatRequest = {
  session_id: string;
  customer_id: string;
  message: string;
  choice?: string;
};

export type ChatResponse = {
  type: "answer" | "clarify" | "unsupported";
  agent: "balance" | "loan" | "interest" | null;
  topic: string | null;
  text: string;
  slots: Record<string, string>;
  options: ChatOption[];
};

// 화면 타입 — 계약 아님
export type CustomerId = "C001" | "C002" | "C003";

export const CUSTOMER_IDS: readonly CustomerId[] = ["C001", "C002", "C003"];

export type ChatMessage = {
  role: "user" | "bot";
  text: string;
  slots?: Record<string, string>;
  options?: ChatOption[];
  error?: true;
};
