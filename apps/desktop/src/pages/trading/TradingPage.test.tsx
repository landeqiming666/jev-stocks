import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useAppStore } from "../../app/store";
import { RpcError } from "../../rpc";
import { RouterView } from "../../router/RouterView";
import TradingPage from "./index";
import { deferred, fakeClient, orders, pending, portfolio } from "./test-support";

afterEach(() => { cleanup(); useAppStore.getState().reset(); window.location.hash = ""; });
function mount(handler?: Parameters<typeof fakeClient>[0], strict = false) {
  const fake = fakeClient(handler);
  useAppStore.setState({ client: fake.client });
  const view = render(strict ? <StrictMode><TradingPage /></StrictMode> : <TradingPage />);
  return { ...fake, ...view };
}
const ready = () => waitFor(() => expect(document.querySelector('.p-trading[data-ready="true"]')).toBeTruthy());
it("trading_default_renders_four_metric_cards", async () => {
  mount();
  await ready();
  await screen.findByText("现金");
  for (const label of ["冻结资金", "持仓市值", "权益"]) expect(screen.getByText(label)).toBeTruthy();
  expect(document.querySelector('[data-ready="true"]')).toBeTruthy();
});
it("trading_advance_updates_clock_and_toast", async () => {
  const next = { ...portfolio, account: { ...portfolio.account, clockDate: "2026-10-30" }, asOf: "2026-10-30" };
  let advanced = false;
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  const fake = mount(method => {
    if (method === "paper.advance") { advanced = true; return { clockDate: "2026-10-30", tradingDay: true, filled: [pending], rejected: [], pendingRemaining: 0, portfolio: next }; }
    if (method === "paper.portfolio" && advanced) return next;
  });
  fireEvent.click(await screen.findByRole("button", { name: "下一交易日" }));
  await screen.findByText("2026-10-30（周五）");
  await waitFor(() => expect(toast).toHaveBeenCalled());
  expect((toast.mock.calls[0]![0] as CustomEvent).detail).toMatchObject({ tone: "success", text: expect.stringContaining("1 笔成交") });
  expect(fake.calls.filter(call => call.method === "paper.portfolio")).toHaveLength(2);
  window.removeEventListener("sentinel:toast", toast);
});
it("trading_no_price_keeps_clock", async () => {
  mount(method => { if (method === "paper.advance") throw new RpcError("DATA_INSUFFICIENT", "没有 2026-11-02 的行情。请先刷新行情。", false, { nextDay: "2026-11-02" }); });
  await waitFor(() => expect(document.querySelector(".p-trading__clock")?.textContent).toContain(portfolio.account.clockDate));
  fireEvent.click(screen.getByRole("button", { name: "下一交易日" }));
  await screen.findByText("没有 2026-11-02 的行情。请先刷新行情。");
  expect(document.querySelector(".p-trading__clock")?.textContent).toContain(portfolio.account.clockDate);
  expect(document.querySelector(".c-banner--warn")).toBeTruthy();
});
it("rejects with a real orderId, refreshes history and emits no success toast", async () => {
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  mount(method => { if (method === "paper.order.place") throw new RpcError("ORDER_REJECTED", "资金不足：预计需要 $92,025.99，可用现金 $90,185.09。", false, { orderId: pending.orderId }); });
  const search = await screen.findByRole("combobox", { name: "标的" });
  fireEvent.change(search, { target: { value: "zz" } });
  fireEvent.click(within(await screen.findByRole("listbox")).getByRole("option"));
  fireEvent.click(screen.getByRole("button", { name: "提交订单" }));
  await waitFor(() => expect(screen.getAllByText(/预计需要 \$92,025.99/).length).toBeGreaterThan(0));
  expect(screen.getByRole("tab", { name: "历史订单" }).getAttribute("aria-selected")).toBe("true");
  expect(document.querySelector(`[data-order-id="${pending.orderId}"].is-selected`)).toBeTruthy();
  expect(toast).not.toHaveBeenCalled();
  window.removeEventListener("sentinel:toast", toast);
});
it("discard old account responses and late mutations after account switching", async () => {
  const old = deferred<typeof portfolio>();
  const accountB = { ...portfolio.account, accountId: "account-b", name: "B" };
  const fake = mount((method, params) => {
    if (method === "paper.accounts") return { items: [portfolio.account, accountB] };
    if (method === "paper.portfolio") return params.accountId === accountB.accountId ? { ...portfolio, account: accountB, cash: "7.0000" } : old.promise;
  });
  fireEvent.change(await screen.findByLabelText("账户"), { target: { value: accountB.accountId } });
  await screen.findByText("$7.00");
  await act(async () => { old.resolve(portfolio); });
  expect(screen.getByText("$7.00")).toBeTruthy();
  expect(fake.calls.find(call => call.method === "paper.portfolio")!.signal?.aborted).toBe(true);
});
it("StrictMode setup survives and unmount aborts reads without disposing shared client", async () => {
  const fake = mount(undefined, true);
  await ready();
  fake.unmount();
  expect(fake.isDisposed()).toBe(false);
  expect(fake.calls.every(call => call.signal?.aborted)).toBe(true);
});
it("loads every order page, and cancels only once on double click", async () => {
  const response = deferred<typeof pending>();
  const fake = mount((method, params) => {
    if (method === "paper.orders") return { items: params.cursor ? [orders[1]] : [pending], nextCursor: params.cursor ? null : "next" };
    if (method === "paper.order.cancel") return response.promise;
  });
  const cancel = await screen.findByRole("button", { name: "取消订单" });
  fireEvent.click(cancel); fireEvent.click(cancel);
  expect(fake.calls.filter(call => call.method === "paper.order.cancel")).toHaveLength(1);
  await act(async () => { response.resolve({ ...pending, status: "cancelled" }); });
});
it("a late advance response cannot switch the new account tab or show a toast", async () => {
  const response = deferred<unknown>();
  const accountB = { ...portfolio.account, accountId: "account-b", name: "B" };
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  mount((method, params) => {
    if (method === "paper.accounts") return { items: [portfolio.account, accountB] };
    if (method === "paper.portfolio" && params.accountId === "account-b") return { ...portfolio, account: accountB };
    if (method === "paper.advance") return response.promise;
  });
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "下一交易日" }));
  fireEvent.change(screen.getByLabelText("账户"), { target: { value: "account-b" } });
  await ready();
  await act(async () => { response.resolve({ clockDate: "2026-10-30", portfolio, filled: [pending], rejected: [], pendingRemaining: 0, tradingDay: true }); });
  expect((screen.getByLabelText("账户") as HTMLSelectElement).value).toBe("account-b");
  expect(screen.getByRole("tab", { name: "挂单" }).getAttribute("aria-selected")).toBe("true");
  expect(toast).not.toHaveBeenCalled();
  window.removeEventListener("sentinel:toast", toast);
});
it("an unresolved timeout survives unmount and remount of the same shared client", async () => {
  const fake = mount(method => { if (method === "paper.order.place") throw new RpcError("TIMEOUT", "请求超时"); });
  const search = await screen.findByRole("combobox", { name: "标的" });
  fireEvent.change(search, { target: { value: "zz" } });
  fireEvent.click(within(await screen.findByRole("listbox")).getByRole("option"));
  fireEvent.click(screen.getByRole("button", { name: "提交订单" }));
  await screen.findByRole("button", { name: "查询并重试原订单" });
  const key = fake.calls.find(call => call.method === "paper.order.place")!.params.idempotencyKey;
  fake.unmount(); render(<TradingPage />);
  fireEvent.click(await screen.findByRole("button", { name: "查询并重试原订单" }));
  await waitFor(() => expect(fake.calls.some(call => call.method === "paper.orders" && call.params.idempotencyKey === key)).toBe(true));
});
it("account missing during a write returns to the account creation state", async () => {
  mount(method => { if (method === "paper.advance") throw new RpcError("NOT_FOUND", "账户不存在", false, { field: "accountId" }); });
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "下一交易日" }));
  await screen.findByRole("heading", { name: "创建模拟账户" });
  expect(screen.queryByLabelText("账户")).toBeNull();
});
it("RouterView discovers the actual default export and hash state cannot replace real data", async () => {
  window.location.hash = "#/trading?state=no_account";
  useAppStore.setState({ client: fakeClient().client });
  render(<RouterView />);
  await ready();
  expect(document.querySelector(".p-trading")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "创建模拟账户" })).toBeNull();
});
it("a stale account list followed by NOT_FOUND does not leave an unusable account selected", async () => {
  mount(method => { if (method === "paper.portfolio") throw new RpcError("NOT_FOUND", "账户不存在", false, { field: "accountId" }); });
  await screen.findByRole("heading", { name: "创建模拟账户" });
  expect(screen.queryByLabelText("账户")).toBeNull();
});
it("advance rejection displays the real reason and id while retaining the committed clock", async () => {
  const denied = { ...pending, status: "rejected" as const, rejectReason: { code: "INSUFFICIENT_CASH_AT_FILL" as const,
    message: "开盘价高于预估，资金不足：需要 $98,000.00，可用 $90,185.09。" } };
  const next = { ...portfolio, account: { ...portfolio.account, clockDate: "2026-10-30" }, asOf: "2026-10-30" };
  let advanced = false;
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  mount(method => {
    if (method === "paper.advance") { advanced = true; return { clockDate: "2026-10-30", tradingDay: true, filled: [], rejected: [denied], pendingRemaining: 0, portfolio: next }; }
    if (method === "paper.portfolio" && advanced) return next;
    if (method === "paper.orders" && advanced) return { items: [denied], nextCursor: null };
  });
  await ready(); fireEvent.click(screen.getByRole("button", { name: "下一交易日" }));
  await screen.findByText("2026-10-30（周五）");
  await waitFor(() => expect(document.querySelector("tr.is-selected")?.textContent).toContain("$98,000.00"));
  expect(document.querySelector("tr.is-selected")?.textContent).toContain(pending.orderId);
  expect(toast).not.toHaveBeenCalled(); window.removeEventListener("sentinel:toast", toast);
});
