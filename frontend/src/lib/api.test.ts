import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatRequest, ChatResponse } from "../types/chat";
import { sendChat } from "./api";

const REQ: ChatRequest = {
  session_id: "s-1",
  customer_id: "C001",
  message: "잔액 얼마예요?",
};

const RES: ChatResponse = {
  type: "answer",
  agent: "balance",
  topic: "balance",
  text: "현재 잔액은 {{balance}}입니다.",
  slots: { balance: "1,234,567원" },
  options: [],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

function sentInit(): RequestInit {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  return fetchMock.mock.calls[0][1] ?? {};
}

function sentBody(): Record<string, unknown> {
  return JSON.parse(String(sentInit().body));
}

describe("sendChat", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse(RES));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("요청 형태", () => {
    it("상대경로 /api/chat에 POST로 JSON을 보낸다", async () => {
      await sendChat(REQ);

      expect(fetchMock.mock.calls[0][0]).toBe("/api/chat");
      const init = sentInit();
      expect(init.method).toBe("POST");
      expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
      expect(sentBody()).toEqual(REQ);
    });

    it("choice가 없는 요청의 본문에는 choice 키가 없다", async () => {
      await sendChat(REQ);

      expect("choice" in sentBody()).toBe(false);
    });

    it("choice가 있는 요청의 본문에는 choice가 그대로 들어간다", async () => {
      const req: ChatRequest = { ...REQ, message: "잔액조회", choice: "balance" };

      await sendChat(req);

      expect(sentBody()).toEqual(req);
      expect(sentBody().choice).toBe("balance");
    });
  });

  describe("응답 처리", () => {
    it("2xx 응답이면 응답 JSON을 돌려준다", async () => {
      await expect(sendChat(REQ)).resolves.toEqual(RES);
    });

    it.each([500, 404])("%i 응답이면 reject하고 다시 요청하지 않는다", async (status) => {
      fetchMock.mockResolvedValue(jsonResponse({ detail: "error" }, status));

      await expect(sendChat(REQ)).rejects.toThrow();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("fetch가 reject하면(네트워크 오류) reject하고 다시 요청하지 않는다", async () => {
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

      await expect(sendChat(REQ)).rejects.toThrow();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });
});
