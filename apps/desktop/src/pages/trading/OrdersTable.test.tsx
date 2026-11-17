import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OrdersTable } from "./OrdersTable";
import { orders, portfolio, rejected } from "./test-support";

afterEach(cleanup);
it("trading_rejected_order_appears_in_history", () => {
  render(<OrdersTable tab="history" orders={orders} positions={portfolio.positions} busy={false} onCancel={async () => {}} onTab={() => {}} />);
  expect(screen.getByText("已拒绝")).toBeTruthy();
  expect(screen.getByText(rejected.rejectReason!.message)).toBeTruthy();
});
it("tabs support arrows and a roving tab stop", () => {
  const onTab = vi.fn();
  render(<OrdersTable tab="pending" orders={[]} positions={[]} busy={false} onCancel={async () => {}} onTab={onTab} />);
  fireEvent.keyDown(screen.getByRole("tab", { name: "挂单" }), { key: "ArrowRight" });
  expect(onTab).toHaveBeenCalledWith("fills");
  expect(document.activeElement).toBe(screen.getByRole("tab", { name: "成交" }));
});
