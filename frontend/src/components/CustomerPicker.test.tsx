import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CustomerId } from "../types/chat";
import { CustomerPicker } from "./CustomerPicker";

describe("CustomerPicker", () => {
  it("'데모 고객' 선택 상자에 C001·C002·C003이 순서대로 있고 value가 선택돼 있다", () => {
    render(<CustomerPicker value="C003" disabled={false} onChange={() => {}} />);

    const select = screen.getByLabelText("데모 고객");
    expect(select).toBe(screen.getByRole("combobox"));
    const options = within(select).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["C001", "C002", "C003"]);
    expect(options.map((o) => (o as HTMLOptionElement).value)).toEqual(["C001", "C002", "C003"]);
    expect(select).toHaveValue("C003");
    expect(select).toBeEnabled();
  });

  it("C002를 고르면 onChange가 'C002'로 한 번 불린다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(id: CustomerId) => void>();
    render(<CustomerPicker value="C001" disabled={false} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("데모 고객"), "C002");

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("C002");
  });

  it("disabled면 선택 상자가 비활성이다", () => {
    render(<CustomerPicker value="C001" disabled={true} onChange={() => {}} />);

    expect(screen.getByLabelText("데모 고객")).toBeDisabled();
  });
});
