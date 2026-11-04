import { useCallback, useEffect, useRef, useState } from "react";
import { notifyToast, REFRESH_EVENT } from "../../app/events";
import { trading as t } from "../../i18n/zh-CN/trading";
import { RpcError, type PaperAccount, type PaperOrder, type Portfolio, type RpcClient, type ParamsOf } from "../../rpc";
import { getOrderIntents, type PendingIntent, type PlaceOrderInput } from "./order-intents";

type View = { accounts: PaperAccount[]; account: PaperAccount | null; portfolio: Portfolio | null; orders: PaperOrder[];
  loading: boolean; busy: boolean; error: RpcError | null; unresolved: PendingIntent | null; highlight: string | null };
type Session = { active: boolean; id: string | null; revision: number; client: RpcClient; view: View;
  reads: Set<AbortController>; actions: Set<AbortController> };
const empty = (): View => ({ accounts: [], account: null, portfolio: null, orders: [], loading: true, busy: false,
  error: null, unresolved: null, highlight: null });
const rpcError = (error: unknown) => error instanceof RpcError ? error : new RpcError("INTERNAL", t.failed);

export function usePaper(client: RpcClient | null) {
  const [view, setView] = useState<View>(empty);
  const session = useRef<Session | null>(null);
  const publish = useCallback((s: Session, values: Partial<View>) => {
    if (!s.active || session.current !== s) return;
    s.view = { ...s.view, ...values }; setView(s.view);
  }, []);
  const load = useCallback(async (s: Session, id: string, revision: number) => {
    const controller = new AbortController(); s.reads.add(controller);
    try {
      const allOrders = async () => {
        const items: PaperOrder[] = []; const seen = new Set<string>(); let cursor: string | undefined;
        do {
          const page = await s.client.call("paper.orders", { accountId: id, limit: 200, ...(cursor ? { cursor } : {}) }, { signal: controller.signal });
          items.push(...page.items); cursor = page.nextCursor ?? undefined;
          if (cursor && seen.has(cursor)) throw new RpcError("INTERNAL", t.invalidPagination);
          if (cursor) seen.add(cursor);
        } while (cursor && !controller.signal.aborted);
        return items;
      };
      const [portfolio, orders] = await Promise.all([
        s.client.call("paper.portfolio", { accountId: id }, { signal: controller.signal }), allOrders(),
      ]);
      if (s.active && s.id === id && s.revision === revision && !controller.signal.aborted)
        publish(s, { portfolio, account: portfolio.account, orders, loading: false,
          accounts: s.view.accounts.map(account => account.accountId === id ? portfolio.account : account) });
    } finally { s.reads.delete(controller); controller.abort(); }
  }, [publish]);
  const select = useCallback((id: string) => {
    const s = session.current; if (!s?.active) return;
    for (const controller of s.reads) controller.abort();
    for (const controller of s.actions) controller.abort();
    s.id = id; s.revision++;
    publish(s, { account: s.view.accounts.find(a => a.accountId === id) ?? null, portfolio: null, orders: [],
      error: null, loading: true, busy: false, highlight: null, unresolved: getOrderIntents(s.client).get(id) });
    const revision = s.revision;
    void load(s, id, revision).catch(error => {
      if (s.id !== id || s.revision !== revision) return;
      const failure = rpcError(error);
      if (failure.code === "NOT_FOUND" && failure.data.field === "accountId") {
        s.id = null;
        publish(s, { account: null, portfolio: null, orders: [], accounts: s.view.accounts.filter(account => account.accountId !== id) });
      }
      publish(s, { loading: false, error: failure });
    });
  }, [load, publish]);
  const refresh = useCallback(async () => {
    const s = session.current; if (!s?.active || s.view.busy) return;
    const revision = ++s.revision;
    for (const controller of s.reads) controller.abort();
    const controller = new AbortController(); s.reads.add(controller);
    try {
      const result = await s.client.call("paper.accounts", {}, { signal: controller.signal });
      if (!s.active || controller.signal.aborted || s.revision !== revision) return;
      const id = result.items.some(a => a.accountId === s.id) ? s.id! : result.items[0]?.accountId;
      publish(s, { accounts: result.items, error: null });
      if (!id) { s.id = null; publish(s, { ...empty(), accounts: result.items, loading: false }); return; }
      if (s.id !== id) { select(id); return; }
      await load(s, id, revision);
    } catch (error) {
      if (s.revision === revision && !controller.signal.aborted) {
        const failure = rpcError(error);
        if (failure.code === "NOT_FOUND" && failure.data.field === "accountId") {
          const id = s.id; s.id = null;
          publish(s, { account: null, portfolio: null, orders: [], accounts: s.view.accounts.filter(account => account.accountId !== id) });
        }
        publish(s, { error: failure, loading: false });
      }
    } finally { s.reads.delete(controller); controller.abort(); }
  }, [load, publish, select]);
  useEffect(() => {
    if (!client) { setView({ ...empty(), loading: false }); return; }
    const s: Session = { active: true, id: null, revision: 0, client, view: empty(), reads: new Set(), actions: new Set() };
    session.current = s; setView(s.view); void refresh();
    const onFocus = () => { void refresh(); };
    const onRefresh = (event: Event) => {
      const scope = (event as CustomEvent<{ scope?: string }>).detail?.scope;
      if (!scope || scope === "trading" || scope === "paper") void refresh();
    };
    window.addEventListener("focus", onFocus); window.addEventListener(REFRESH_EVENT, onRefresh);
    return () => {
      s.active = false;
      for (const controller of [...s.reads, ...s.actions]) controller.abort();
      window.removeEventListener("focus", onFocus); window.removeEventListener(REFRESH_EVENT, onRefresh);
    };
  }, [client, refresh]);
  const operation = async <T,>(action: (s: Session, id: string, signal: AbortSignal) => Promise<T>, success?: (result: T) => string | null) => {
    const s = session.current;
    if (!s?.active || !s.id || s.view.busy) throw new RpcError("CONFLICT", t.operationBusy);
    const id = s.id, revision = ++s.revision, controller = new AbortController();
    for (const read of s.reads) read.abort();
    s.actions.add(controller); publish(s, { busy: true, error: null });
    const current = () => s.active && s.id === id && s.revision === revision;
    try {
      const result = await action(s, id, controller.signal);
      if (!current()) throw new RpcError("CANCELLED", t.accountMissing);
      const message = success?.(result);
      if (message) notifyToast("success", message);
      try { await load(s, id, revision); }
      catch { if (current()) publish(s, { error: new RpcError("INTERNAL", t.refreshFailed), loading: false }); }
      return result;
    } catch (error) {
      const failure = rpcError(error);
      if (current()) {
        publish(s, { error: failure, highlight: typeof failure.data.orderId === "string" ? failure.data.orderId : null });
        if (failure.code === "NOT_FOUND" && failure.data.field === "accountId") {
          s.id = null;
          publish(s, { account: null, portfolio: null, orders: [], busy: false, loading: false,
            accounts: s.view.accounts.filter(account => account.accountId !== id) });
        }
        if (failure.code === "ORDER_REJECTED") {
          try { await load(s, id, revision); } catch { /* 原拒单和编号优先于刷新错误。 */ }
        }
      }
      throw failure;
    } finally {
      s.actions.delete(controller); controller.abort();
      if (current()) publish(s, { busy: false, unresolved: getOrderIntents(s.client).get(id) });
    }
  };
  const place = (input: PlaceOrderInput) => operation((s, id, signal) => getOrderIntents(s.client).place(id, input, signal),
    order => order.status === "filled" || order.status === "cancelled" ? t.orderConfirmed(order.status) : t.orderDone);
  const advance = () => operation(async (s, id, signal) => {
    const result = await s.client.call("paper.advance", { accountId: id }, { signal });
    if (s.active && s.id === id && !signal.aborted) {
      const rejected = result.rejected[0];
      publish(s, { account: result.portfolio.account, portfolio: result.portfolio,
        orders: [...result.filled, ...result.rejected, ...s.view.orders.filter(order => ![...result.filled, ...result.rejected].some(changed => changed.orderId === order.orderId))],
        ...(rejected ? { highlight: rejected.orderId, error: new RpcError("ORDER_REJECTED", rejected.rejectReason?.message ?? t.failed, false, { orderId: rejected.orderId }) } : {}) });
    }
    return result;
  }, result => result.rejected.length ? null : t.advanceDone(result.clockDate, result.filled.length, 0));
  const cancel = (orderId: string) => operation((s, _id, signal) => s.client.call("paper.order.cancel", { orderId }, { signal }), () => t.cancelled);
  const reset = (confirmText: string) => operation((s, id, signal) => s.client.call("paper.reset", { accountId: id, confirmText }, { signal }), () => t.resetDone);
  const create = async (input: ParamsOf<"paper.createAccount">) => {
    const s = session.current;
    if (!s?.active || s.view.busy) throw new RpcError("CONFLICT", t.operationBusy);
    const revision = ++s.revision;
    for (const read of s.reads) read.abort();
    const controller = new AbortController(); s.actions.add(controller); publish(s, { busy: true, error: null });
    try {
      const account = await s.client.call("paper.createAccount", input, { signal: controller.signal });
      if (!s.active || controller.signal.aborted) throw new RpcError("CANCELLED", t.accountMissing);
      publish(s, { accounts: [...s.view.accounts, account], busy: false }); select(account.accountId);
    } catch (error) {
      if (s.active && s.revision === revision && !controller.signal.aborted) publish(s, { error: rpcError(error) });
      throw error;
    } finally {
      s.actions.delete(controller); controller.abort();
      if (s.active && s.revision === revision) publish(s, { busy: false });
    }
  };
  const clearHighlight = () => { const s = session.current; if (s) publish(s, { highlight: null }); };
  return { ...view, select, refresh, place, advance, cancel, reset, create, clearHighlight };
}
