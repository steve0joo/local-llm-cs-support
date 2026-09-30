import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatOption } from "../types/chat";
import { OptionButtons } from "./OptionButtons";

const OPTIONS: ChatOption[] = [
  { label: "대출문의", choice: "loan" },
  { label: "이자/연체", choice: "interest" },
];

describe("OptionButtons", () => {
  it("선택지마다 label 텍스트의 버튼을 하나씩 그린다", () => {
    render(<OptionButtons options={OPTIONS} disabled={false} onSelect={() => {}} />);

    expect(screen.getAllByRole("button")).toHaveLength(OPTIONS.length);
    for (const option of OPTIONS) {
      const button = screen.getByRole("button", { name: option.label });
      expect(button).toBeEnabled();
      expect(button).toHaveAttribute("type", "button");
    }
  });

  it("버튼을 누르면 onSelect가 그 선택지 객체로 한 번 불린다", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn<(option: ChatOption) => void>();
    render(<OptionButtons options={OPTIONS} disabled={false} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: "이자/연체" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith({ label: "이자/연체", choice: "interest" });
  });

  it("disabled면 모든 버튼이 비활성이고 눌러도 onSelect가 불리지 않는다", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn<(option: ChatOption) => void>();
    render(<OptionButtons options={OPTIONS} disabled={true} onSelect={onSelect} />);

    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
      await user.click(button);
    }

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("options가 빈 배열이면 버튼을 그리지 않는다", () => {
    render(<OptionButtons options={[]} disabled={false} onSelect={() => {}} />);

    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
