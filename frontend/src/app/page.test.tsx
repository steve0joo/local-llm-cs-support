import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sendChat } from "../lib/api";
import type { ChatResponse } from "../types/chat";
import Page from "./page";

vi.mock("../lib/api", () => ({ sendChat: vi.fn() }));
vi.mock("../components/ScrollWorld", () => ({ ScrollWorld: () => null }));

const sendChatMock = vi.mocked(sendChat);

const GUIDE = "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요.";

const BALANCE: ChatResponse = {
  type: "answer",
  agent: "balance",
  topic: "balance",
  text: "현재 잔액은 {{balance}}입니다.",
  slots: { balance: "1,234,567원" },
  options: [],
};
const CLARIFY: ChatResponse = {
  type: "clarify",
  agent: null,
  topic: null,
  text: "어느 쪽을 먼저 도와드릴까요?",
  slots: {},
  options: [
    { label: "대출문의", choice: "loan" },
    { label: "이자·연체", choice: "interest" },
  ],
};
const INTEREST: ChatResponse = {
  type: "answer",
  agent: "interest",
  topic: "interest",
  text: "이자·연체 문의를 도와드리겠습니다.",
  slots: {},
  options: [],
};

function request(n: number) {
  return sendChatMock.mock.calls[n][0];
}

async function send(u: ReturnType<typeof userEvent.setup>, text: string) {
  await u.type(screen.getByRole("textbox", { name: "메시지" }), `${text}{Enter}`);
}

beforeEach(() => {
  sendChatMock.mockReset();
});

describe("Page", () => {
  it("잔액 응답을 받으면 금액이 치환돼 보이고 {{가 남지 않는다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValueOnce(BALANCE);
    render(<Page />);

    await send(u, "잔액 알려줘");

    expect(await screen.findByText("1,234,567원")).toBeInTheDocument();
    expect(screen.getByText("잔액 알려줘")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("{{");

    expect(sendChatMock).toHaveBeenCalledTimes(1);
    expect(request(0)).toEqual({ session_id: expect.any(String), customer_id: "C001", message: "잔액 알려줘" });
    expect(request(0)).not.toHaveProperty("choice");
  });

  it("clarify 선택지를 누르면 label을 고객 말풍선으로 추가하고 choice를 붙여 같은 세션으로 보낸다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValueOnce(CLARIFY).mockResolvedValueOnce(INTEREST);
    render(<Page />);

    await send(u, "대출 잔액이랑 이자 얼마 남았어요?");
    await u.click(await screen.findByRole("button", { name: "이자·연체" }));

    expect(await screen.findByText("이자·연체 문의를 도와드리겠습니다.")).toBeInTheDocument();
    const bubbles = screen.getAllByText("이자·연체").filter((el) => el.closest("button") === null);
    expect(bubbles).toHaveLength(1);

    expect(sendChatMock).toHaveBeenCalledTimes(2);
    expect(request(0)).not.toHaveProperty("choice");
    expect(request(1)).toEqual({
      session_id: request(0).session_id,
      customer_id: "C001",
      message: "이자·연체",
      choice: "interest",
    });
  });

  it("sendChat이 실패하면 오류 말풍선을 보여주고 입력창을 다시 활성화한다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockRejectedValueOnce(new Error("network"));
    render(<Page />);

    await send(u, "잔액 알려줘");

    expect(await screen.findByText("잠시 후 다시 시도해 주세요")).toHaveClass("text-red-700");
    expect(screen.getByRole("textbox", { name: "메시지" })).toBeEnabled();
  });

  it("요청 중에는 고객 선택과 입력창이 비활성이고, 응답 뒤 다시 활성이다", async () => {
    const u = userEvent.setup();
    let resolve!: (res: ChatResponse) => void;
    sendChatMock.mockReturnValueOnce(
      new Promise<ChatResponse>((r) => {
        resolve = r;
      }),
    );
    render(<Page />);
    const input = screen.getByRole("textbox", { name: "메시지" });
    const picker = screen.getByRole("combobox", { name: "데모 고객" });

    await send(u, "잔액 알려줘");

    expect(input).toBeDisabled();
    expect(picker).toBeDisabled();
    expect(screen.getByText("답변 작성 중")).toBeInTheDocument();

    await act(async () => resolve(BALANCE));

    expect(screen.getByText("1,234,567원")).toBeInTheDocument();
    expect(input).toBeEnabled();
    expect(picker).toBeEnabled();
    expect(screen.queryByText("답변 작성 중")).not.toBeInTheDocument();
  });

  it("고객을 바꾸면 대화가 비고, 다음 요청은 새 고객·새 session_id로 나간다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValueOnce(BALANCE).mockResolvedValueOnce(BALANCE);
    render(<Page />);

    await send(u, "잔액 알려줘");
    await screen.findByText("1,234,567원");

    await u.selectOptions(screen.getByRole("combobox", { name: "데모 고객" }), "C002");

    expect(screen.getByRole("log").textContent).toBe(GUIDE);

    await send(u, "잔액 알려줘");
    await screen.findByText("1,234,567원");

    expect(sendChatMock).toHaveBeenCalledTimes(2);
    expect(request(1).customer_id).toBe("C002");
    expect(request(1).session_id).toEqual(expect.any(String));
    expect(request(1).session_id).not.toBe(request(0).session_id);
  });

  it("#chat 섹션에 카피·데모 고객 선택·새 대화·입력창이 있다", () => {
    render(<Page />);
    const section = document.getElementById("chat") as HTMLElement;
    expect(section).toBeInTheDocument();

    expect(section).toContainElement(screen.getByRole("heading", { level: 2, name: "데모 고객으로 물어보세요." }));
    expect(section).toContainElement(screen.getByText(/실제 개인정보는 입력하지 마세요\./));
    expect(section).toContainElement(screen.getByRole("combobox", { name: "데모 고객" }));
    expect(section).toContainElement(screen.getByRole("button", { name: "새 대화" }));
    expect(section).toContainElement(screen.getByRole("textbox", { name: "메시지" }));
  });

  it("페이지의 h1은 Local LLM — 은행 상담 AI 하나다", () => {
    render(<Page />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Local LLM — 은행 상담 AI");
  });

  it("예시 칩을 누르면 choice 없이 한 번 보낸다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValue(BALANCE);
    render(<Page />);

    await u.click(screen.getByRole("button", { name: "잔액 얼마 남았어요?" }));
    await screen.findByText("1,234,567원");

    expect(sendChatMock).toHaveBeenCalledTimes(1);
    expect(request(0)).toEqual({ session_id: expect.any(String), customer_id: "C001", message: "잔액 얼마 남았어요?" });
    expect(request(0)).not.toHaveProperty("choice");
  });

  it("예시 칩을 더블클릭해도 한 번만 보낸다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValue(BALANCE);
    render(<Page />);

    await u.dblClick(screen.getByRole("button", { name: "잔액 얼마 남았어요?" }));
    await screen.findByText("1,234,567원");

    expect(sendChatMock).toHaveBeenCalledTimes(1);
  });

  it("Enter를 연달아 두 번 눌러도 한 번만 보낸다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockResolvedValue(BALANCE);
    render(<Page />);

    await u.type(screen.getByRole("textbox", { name: "메시지" }), "잔액 알려줘{Enter}{Enter}");
    await screen.findByText("1,234,567원");

    expect(sendChatMock).toHaveBeenCalledTimes(1);
  });

  it("새 대화를 누르면 고객은 그대로 대화가 비고 칩이 다시 보이며, 다음 요청은 새 session_id로 나간다", async () => {
    const u = userEvent.setup();
    sendChatMock.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(BALANCE);
    render(<Page />);
    const picker = screen.getByRole("combobox", { name: "데모 고객" });

    await u.selectOptions(picker, "C002");
    await send(u, "잔액 알려줘");
    await screen.findByText("잠시 후 다시 시도해 주세요");

    await u.click(screen.getByRole("button", { name: "새 대화" }));

    expect(screen.getByRole("log").textContent).toBe(GUIDE);
    expect(screen.getByRole("button", { name: "잔액 얼마 남았어요?" })).toBeInTheDocument();
    expect(picker).toHaveValue("C002");

    await send(u, "잔액 알려줘");
    await screen.findByText("1,234,567원");

    expect(sendChatMock).toHaveBeenCalledTimes(2);
    expect(request(0).customer_id).toBe("C002");
    expect(request(1).customer_id).toBe("C002");
    expect(request(1).session_id).toEqual(expect.any(String));
    expect(request(1).session_id).not.toBe(request(0).session_id);
  });

  it("요청 중에는 새 대화 버튼이 비활성이다", async () => {
    const u = userEvent.setup();
    let resolve!: (res: ChatResponse) => void;
    sendChatMock.mockReturnValueOnce(
      new Promise<ChatResponse>((r) => {
        resolve = r;
      }),
    );
    render(<Page />);
    const newChat = screen.getByRole("button", { name: "새 대화" });
    expect(newChat).toBeEnabled();

    await send(u, "잔액 알려줘");

    expect(newChat).toBeDisabled();

    await act(async () => resolve(BALANCE));

    expect(newChat).toBeEnabled();
  });
});
