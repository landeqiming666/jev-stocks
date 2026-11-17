import type { RpcClient, MethodName, ParamsOf, ResultOf, PaperOrder, Portfolio } from "../../rpc";
import portfolioFixture from "./__fixtures__/portfolio.json";
import ordersFixture from "./__fixtures__/orders.json";

export const portfolio = portfolioFixture as Portfolio;
export const orders = ordersFixture.items as PaperOrder[];
export const pending = orders.find(order => order.status === "pending")!;
export const rejected = orders.find(order => order.status === "rejected")!;
export const instrument = pending.instrument;
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (value: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
export type Handler = (method: MethodName, params: Record<string, unknown>, signal?: AbortSignal) => unknown;
export function fakeClient(handler?: Handler) {
  const calls: { method: MethodName; params: Record<string, unknown>; signal?: AbortSignal }[] = [];
  let disposed = false;
  const client: RpcClient = {
    async call<M extends MethodName>(method: M, params: ParamsOf<M>, options = {}): Promise<ResultOf<M>> {
      const signal = (options as { signal?: AbortSignal }).signal;
      calls.push({ method, params, signal });
      const result = handler?.(method, params, signal);
      if (result !== undefined) return await result as ResultOf<M>;
      const defaults: Partial<Record<MethodName, unknown>> = {
        "paper.accounts": { items: [portfolio.account] }, "paper.portfolio": portfolio,
        "paper.orders": { items: orders, nextCursor: null },
        "paper.order.place": pending, "paper.order.cancel": { ...pending, status: "cancelled" },
        "instruments.search": { items: [instrument] }, "paper.reset": { ok: true },
        "paper.createAccount": { ...portfolio.account, name: String((params as Record<string, unknown>).name) },
      };
      if (!(method in defaults)) throw new Error(`Unexpected ${method}`);
      return defaults[method] as ResultOf<M>;
    },
    subscribe: () => () => {}, status: () => "ready", whenReady: async () => {},
    dispose: () => { disposed = true; },
  };
  return { client, calls, isDisposed: () => disposed };
}
