import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, ChatOption } from "../types/chat";
import { ChatWindow } from "./ChatWindow";

const GUIDE = "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요.";

const CLARIFY: ChatMessage = {
  role: "bot",
  text: "어느 쪽을 먼저 도와드릴까요?",
  options: [
    { label: "대출문의", choice: "loan" },
    { label: "이자/연체", choice: "interest" },
  ],
};
const ACCOUNTS: ChatMessage = {
  role: "bot",
  text: "어느 계좌의 잔액을 알려드릴까요?",
  options: [
    { label: "입출금 1", choice: "balance" },
    { label: "입출금 2", choice: "balance" },
  ],
};
const ANSWER: ChatMessage = { role: "bot", text: "현재 잔액은 {{balance}}입니다.", slots: { balance: "1,234,567원" } };
const ERROR: ChatMessage = { role: "bot", text: "잠시 후 다시 시도해 주세요", error: true };
const user = (text: string): ChatMessage => ({ role: "user", text });

function setup(messages: ChatMessage[], pending = false) {
  const onSend = vi.fn<(text: string) => void>();
  const onSelect = vi.fn<(option: ChatOption) => void>();
  const view = (m: ChatMessage[], p: boolean) => (
    <ChatWindow messages={m} pending={p} onSend={onSend} onSelect={onSelect} />
  );
  const { rerender } = render(view(messages, pending));
  return { onSend, onSelect, rerender: (m: ChatMessage[], p: boolean) => rerender(view(m, p)) };
}

function expectButtons(labels: string[], enabled: boolean) {
  for (const label of labels) {
    const button = screen.getByRole("button", { name: label });
    if (enabled) {
      expect(button).toBeEnabled();
    } else {
      expect(button).toBeDisabled();
    }
  }
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatWindow", () => {
  it("messages가 비었으면 첫 화면 안내 문구를 보여주고, 메시지가 있으면 보여주지 않는다", () => {
    const { rerender } = setup([]);
    expect(screen.getByText(GUIDE)).toBeInTheDocument();

    rerender([user("잔액 알려줘")], false);
    expect(screen.queryByText(GUIDE)).not.toBeInTheDocument();
  });

  it("Enter를 누르면 trim한 입력으로 onSend가 한 번 불리고 입력창이 빈다", async () => {
    const u = userEvent.setup();
    const { onSend } = setup([]);
    const input = screen.getByRole("textbox");

    await u.type(input, "  잔액 알려줘  {Enter}");

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("잔액 알려줘");
    expect(input).toHaveValue("");
  });

  it("전송 버튼을 눌러도 trim한 입력으로 onSend가 한 번 불리고 입력창이 빈다", async () => {
    const u = userEvent.setup();
    const { onSend } = setup([]);
    const input = screen.getByRole("textbox");

    await u.type(input, "  잔액 알려줘  ");
    await u.click(screen.getByRole("button", { name: "전송" }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("잔액 알려줘");
    expect(input).toHaveValue("");
  });

  it("공백만 입력하면 전송 버튼이 비활성이고 Enter를 눌러도 onSend가 불리지 않는다", async () => {
    const u = userEvent.setup();
    const { onSend } = setup([]);
    const input = screen.getByRole("textbox");

    await u.type(input, "   ");
    expect(screen.getByRole("button", { name: "전송" })).toBeDisabled();

    await u.type(input, "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("pending이면 입력창·전송 버튼·모든 선택지가 비활성이고 입력 중 표시가 보인다", () => {
    const { rerender } = setup([CLARIFY, user("대출문의"), ACCOUNTS], false);
    expect(screen.queryByText("답변 작성 중")).not.toBeInTheDocument();

    rerender([CLARIFY, user("대출문의"), ACCOUNTS], true);

    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "전송" })).toBeDisabled();
    expectButtons(["대출문의", "이자/연체", "입출금 1", "입출금 2"], false);
    expect(screen.getByText("답변 작성 중")).toBeInTheDocument();
  });

  it("선택지가 있는 봇 메시지가 둘이면 마지막 것의 선택지만 활성이다", () => {
    setup([CLARIFY, user("대출문의"), ACCOUNTS]);

    expectButtons(["대출문의", "이자/연체"], false);
    expectButtons(["입출금 1", "입출금 2"], true);
  });

  it("선택지 있는 봇 메시지 뒤에 오류 봇 메시지만 있으면 그 선택지는 활성이다(FE-007)", () => {
    setup([CLARIFY, user("대출문의"), ERROR]);

    expectButtons(["대출문의", "이자/연체"], true);
  });

  it("마지막 메시지가 고객 말풍선이어도 마지막 봇 메시지의 선택지는 활성이다", () => {
    setup([ACCOUNTS, user("입출금 1")]);

    expectButtons(["입출금 1", "입출금 2"], true);
  });

  it("선택지 있는 봇 메시지 뒤에 오류가 아닌 봇 메시지가 오면 그 선택지는 비활성이다", () => {
    setup([ACCOUNTS, user("입출금 1"), ANSWER]);

    expectButtons(["입출금 1", "입출금 2"], false);
  });

  it("활성 선택지를 누르면 onSelect가 그 선택지 객체로 한 번 불린다", async () => {
    const u = userEvent.setup();
    const { onSelect } = setup([CLARIFY]);

    await u.click(screen.getByRole("button", { name: "이자/연체" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith({ label: "이자/연체", choice: "interest" });
  });

  it("메시지가 늘거나 pending이 바뀌면 대화 목록의 scrollTop을 scrollHeight로 내린다", () => {
    vi.spyOn(Element.prototype, "scrollHeight", "get").mockReturnValue(480);
    const { rerender } = setup([user("잔액 알려줘")]);
    const list = screen.getByRole("log");
    expect(list.scrollTop).toBe(480);

    list.scrollTop = 0;
    rerender([user("잔액 알려줘")], true);
    expect(list.scrollTop).toBe(480);

    list.scrollTop = 0;
    rerender([user("잔액 알려줘"), ANSWER], false);
    expect(list.scrollTop).toBe(480);
  });
});
