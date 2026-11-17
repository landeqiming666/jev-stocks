import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RpcError } from "../../rpc";
import { OrderPanel } from "./OrderPanel";
import { OrderIntents } from "./order-intents";
import { deferred, fakeClient, instrument, orders, pending, portfolio } from "./test-support";

afterEach(cleanup);
const input = { instrumentId: instrument.instrumentId, side: "buy" as const, quantity: 100, orderType: "market_open" as const };
it("trading_zero_quantity_blocks_submit", async () => {
  const onSubmit = vi.fn();
  render(<OrderPanel client={fakeClient().client} portfolio={portfolio} orders={[]} busy={false} unresolved={null} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByLabelText("数量（股）"), { target: { value: "0" } });
  fireEvent.submit(screen.getByRole("button", { name: "提交订单" }).closest("form")!);
  expect(await screen.findByText("数量必须是 1 至 1,000,000 的正整数")).toBeTruthy();
  expect(onSubmit).not.toHaveBeenCalled();
});
it("trading_place_reuses_idempotency_key_on_timeout", async () => {
  let attempts = 0;
  const fake = fakeClient((method, params) => {
    if (method === "paper.orders") return { items: [], nextCursor: null };
    if (method === "paper.order.place") {
      if (++attempts === 1) throw new RpcError("TIMEOUT", "请求超时");
      return { ...pending, idempotencyKey: params.idempotencyKey };
    }
  });
  const intents = new OrderIntents(fake.client);
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toMatchObject({ code: "TIMEOUT" });
  await intents.place(portfolio.account.accountId, input);
  expect(fake.calls.map(call => call.method)).toEqual(["paper.order.place", "paper.orders", "paper.order.place"]);
  expect(fake.calls[0]!.params.idempotencyKey).toBe(fake.calls[2]!.params.idempotencyKey);
});
it("queries the original key and never resends an already stored order", async () => {
  const fake = fakeClient((method, params) => {
    if (method === "paper.order.place") throw new RpcError("TIMEOUT", "请求超时");
    if (method === "paper.orders") return { items: [{ ...pending, idempotencyKey: params.idempotencyKey }], nextCursor: null };
  });
  const intents = new OrderIntents(fake.client);
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toBeTruthy();
  await intents.place(portfolio.account.accountId, input);
  expect(fake.calls.filter(call => call.method === "paper.order.place")).toHaveLength(1);
});
it("doubleclick locks the same intent and a later explicit intent has a fresh key", async () => {
  const response = deferred<typeof pending>();
  const fake = fakeClient((method, params) => method === "paper.order.place" ? response.promise.then(() => ({ ...pending, idempotencyKey: String(params.idempotencyKey) })) : undefined);
  const intents = new OrderIntents(fake.client);
  const first = intents.place(portfolio.account.accountId, input);
  const second = intents.place(portfolio.account.accountId, input);
  response.resolve(pending);
  await Promise.all([first, second]);
  await intents.place(portfolio.account.accountId, input);
  expect(fake.calls).toHaveLength(2);
  expect(fake.calls[0]!.params.idempotencyKey).not.toBe(fake.calls[1]!.params.idempotencyKey);
});
it("a failed key lookup cannot place again or replace an unresolved intent", async () => {
  const fake = fakeClient(() => { throw new RpcError("TIMEOUT", "请求超时"); });
  const intents = new OrderIntents(fake.client);
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toBeTruthy();
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toBeTruthy();
  await expect(intents.place(portfolio.account.accountId, { ...input, quantity: 101 })).rejects.toMatchObject({ code: "CONFLICT" });
  expect(fake.calls.filter(call => call.method === "paper.order.place")).toHaveLength(1);
});
it("a recovered rejected order stays rejected and preserves its real orderId", async () => {
  const fake = fakeClient((method, params) => {
    if (method === "paper.order.place") throw new RpcError("TIMEOUT", "请求超时");
    return { items: [{ ...pending, idempotencyKey: params.idempotencyKey, status: "rejected",
      rejectReason: { code: "INSUFFICIENT_CASH", message: "资金不足：需要 $100.00" } }], nextCursor: null };
  });
  const intents = new OrderIntents(fake.client);
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toBeTruthy();
  await expect(intents.place(portfolio.account.accountId, input)).rejects.toMatchObject({ code: "ORDER_REJECTED", data: { orderId: pending.orderId } });
});
it("search drops late results and cancels on unmount", async () => {
  const late = deferred<{ items: typeof instrument[] }>();
  const fake = fakeClient((method, params) => method === "instruments.search" ? params.query === "old" ? late.promise : { items: [] } : undefined);
  const view = render(<OrderPanel client={fake.client} portfolio={portfolio} orders={[]} busy={false} unresolved={null} onSubmit={async () => {}} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "old" } });
  await waitFor(() => expect(fake.calls).toHaveLength(1));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "new" } });
  await screen.findByText("没有找到匹配的美股标的");
  late.resolve({ items: [instrument] });
  await waitFor(() => expect(screen.queryByRole("option")).toBeNull());
  view.unmount();
  expect(fake.calls[0]!.signal?.aborted).toBe(true);
});
it("sell without a position shows the actual requested quantity and sends no order", async () => {
  const onSubmit = vi.fn();
  render(<OrderPanel client={fakeClient().client} portfolio={{ ...portfolio, positions: [] }} orders={[]} busy={false} unresolved={null} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole("radio", { name: "卖出" }));
  fireEvent.change(screen.getByLabelText("数量（股）"), { target: { value: "500" } });
  fireEvent.submit(screen.getByRole("button", { name: "提交订单" }).closest("form")!);
  expect(await screen.findByText("可卖数量不足：可卖 0 股，要卖出 500 股。")).toBeTruthy();
  expect(onSubmit).not.toHaveBeenCalled();
});
it("shows exact backend historical estimate as a reference, not a new quote", async () => {
  render(<OrderPanel client={fakeClient().client} portfolio={portfolio} orders={orders} busy={false} unresolved={null} onSubmit={async () => {}} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "zz" } });
  fireEvent.click(await screen.findByRole("option"));
  expect(screen.getByText("$2,841.42")).toBeTruthy();
  expect(screen.getByText("这是最近订单当时的预估，不代表本次下单报价。")).toBeTruthy();
});
