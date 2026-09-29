import { getDefaultNormalizer, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../types/chat";
import { MessageBubble } from "./MessageBubble";

function renderBubble(message: ChatMessage) {
  const { container } = render(<MessageBubble message={message} />);
  return container.firstElementChild as HTMLElement;
}

describe("MessageBubble", () => {
  it("봇 메시지의 슬롯을 금액 스타일로 치환하고 {{를 남기지 않는다", () => {
    const message: ChatMessage = {
      role: "bot",
      text: "현재 잔액은 {{balance}}입니다.",
      slots: { balance: "1,234,567원" },
    };
    const before = structuredClone(message);

    const bubble = renderBubble(message);

    const amount = screen.getByText("1,234,567원");
    expect(amount).toHaveClass("font-semibold", "tabular-nums");
    expect(bubble).toHaveTextContent("현재 잔액은 1,234,567원입니다.");
    expect(bubble.textContent).not.toContain("{{");
    expect(bubble).not.toHaveClass("text-red-700");
    expect(message).toEqual(before);
  });

  it("봇 메시지의 누락 슬롯은 '확인할 수 없습니다'로 보이고 금액 스타일이 없다", () => {
    const bubble = renderBubble({
      role: "bot",
      text: "현재 잔액은 {{balance}}입니다.",
      slots: {},
    });

    expect(bubble.textContent).toBe("현재 잔액은 확인할 수 없습니다입니다.");
    expect(bubble.querySelector(".font-semibold, .tabular-nums")).toBeNull();
  });

  it("slots가 없는 봇 메시지는 빈 slots로 치환한다", () => {
    const bubble = renderBubble({ role: "bot", text: "잔액은 {{balance}}입니다." });

    expect(bubble.textContent).toBe("잔액은 확인할 수 없습니다입니다.");
  });

  it("slots가 없는 봇 메시지의 일반 문장은 그대로 보인다", () => {
    const bubble = renderBubble({ role: "bot", text: "무엇을 도와드릴까요?" });

    expect(bubble.textContent).toBe("무엇을 도와드릴까요?");
  });

  it("고객 메시지는 치환하지 않고 글자 그대로 보여준다", () => {
    const bubble = renderBubble({ role: "user", text: "{{balance}} 알려줘" });

    expect(screen.getByText("{{balance}} 알려줘")).toBeInTheDocument();
    expect(bubble.textContent).toBe("{{balance}} 알려줘");
    expect(bubble.textContent).not.toContain("확인할 수 없습니다");
  });

  it("오류 봇 메시지는 오류 색 클래스가 있다", () => {
    const bubble = renderBubble({ role: "bot", text: "잠시 후 다시 시도해 주세요", error: true });

    expect(bubble).toHaveClass("text-red-700");
    expect(bubble.textContent).toBe("잠시 후 다시 시도해 주세요");
  });

  it("text와 슬롯 값의 줄바꿈을 유지하고 여러 줄 슬롯도 금액 스타일을 받는다", () => {
    const history = "09-01 입금 10,000원\n09-02 출금 5,000원";
    const bubble = renderBubble({
      role: "bot",
      text: "최근 거래내역입니다.\n{{history}}",
      slots: { history },
    });

    expect(bubble).toHaveClass("whitespace-pre-line");
    expect(bubble.textContent).toBe(`최근 거래내역입니다.\n${history}`);
    const slot = screen.getByText(history, {
      normalizer: getDefaultNormalizer({ collapseWhitespace: false }),
    });
    expect(slot).toHaveClass("font-semibold", "tabular-nums");
  });

  it("고객 말풍선도 줄바꿈을 유지한다", () => {
    const bubble = renderBubble({ role: "user", text: "첫 줄\n둘째 줄" });

    expect(bubble).toHaveClass("whitespace-pre-line");
    expect(bubble.textContent).toBe("첫 줄\n둘째 줄");
  });

  it("text와 슬롯 값을 HTML로 해석하지 않는다", () => {
    const bubble = renderBubble({
      role: "bot",
      text: "<i>잔액</i> {{balance}}",
      slots: { balance: "<b>1원</b>" },
    });

    expect(bubble.textContent).toBe("<i>잔액</i> <b>1원</b>");
    expect(bubble.querySelector("i, b")).toBeNull();
  });
});
