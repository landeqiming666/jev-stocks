import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ResetAccountModal } from "./ResetAccountModal";
import { portfolio } from "./test-support";

afterEach(cleanup);
it("trading_reset_requires_account_name", () => {
  const reset = vi.fn();
  render(<ResetAccountModal account={portfolio.account} open busy={false} onClose={() => {}} onReset={reset} />);
  const button = screen.getByRole("button", { name: "确认重置" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("输入账户名"), { target: { value: portfolio.account.name } });
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  expect(reset).toHaveBeenCalledWith(portfolio.account.name);
});
it("keeps confirmation and dialog open after backup failure", async () => {
  const close = vi.fn();
  render(<ResetAccountModal account={portfolio.account} open busy={false} onClose={close} onReset={async () => { throw new Error("备份失败"); }} />);
  fireEvent.change(screen.getByLabelText("输入账户名"), { target: { value: portfolio.account.name } });
  fireEvent.click(screen.getByRole("button", { name: "确认重置" }));
  await waitFor(() => expect(screen.getByText("备份失败")).toBeTruthy());
  expect((screen.getByLabelText("输入账户名") as HTMLInputElement).value).toBe(portfolio.account.name);
  expect(close).not.toHaveBeenCalled();
});
