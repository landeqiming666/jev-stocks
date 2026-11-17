import { useCallback, useEffect, useRef, useState } from "react";
import { notifyToast } from "../../app/events";
import { scan } from "../../i18n/zh-CN/scan";
import { RpcError, type RpcClient, type ScanRun, type ResultOf, type ParamsOfNotification } from "../../rpc";
import { active, terminal } from "./format";

export const HISTORY_LIMIT = 50;
export const RETRY_TIMEOUT_MS = 60_000;
export const PROGRESS_THROTTLE_MS = 500;
export type Budget = ResultOf<"scan.history">["budget"];
export type RunDetail = ResultOf<"scan.detail">;
export type ScanProgress = ParamsOfNotification<"scan.progress">;
export interface ScanControl {
  activeRunId: string | null;
  starting: boolean;
  cancelling: boolean;
  start: () => Promise<void>;
  cancel: (runId: string) => Promise<void>;
}
type Session = {
  alive: boolean; controllers: Map<string, AbortController>; revision: number;
  known: Map<string, { run: ScanRun; revision: number }>;
  operations: Set<string>; selected: string | null; pending: string | null; cancelled: Set<string>;
};
const asError = (error: unknown) => error instanceof RpcError ? error : new RpcError("INTERNAL", scan.loadFailed, true);

export function useScanRuns(client: RpcClient | null, fixtureScope = "") {
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [nextCursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<RpcError | null>(null);
  const [actionError, setActionError] = useState<RpcError | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<RpcError | null>(null);
  const [retryErrors, setRetryErrors] = useState<Record<string, RpcError>>({});
  const [retrying, setRetrying] = useState<string[]>([]);
  const [reconciling, setReconciling] = useState<string[]>([]);
  const [progress, setProgress] = useState<Record<string, ScanProgress>>({});
  const [starting, setStarting] = useState(false);
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string[]>([]);
  const session = useRef<Session | null>(null);

  const request = useCallback((s: Session, key: string) => {
    s.controllers.get(key)?.abort();
    const controller = new AbortController();
    s.controllers.set(key, controller);
    return { controller, current: () => s.alive && session.current === s && !controller.signal.aborted && s.controllers.get(key) === controller };
  }, []);
  const accept = useCallback((s: Session, run: ScanRun, revision: number) => {
    const known = s.known.get(run.runId);
    if (known) {
      const terminalChange = terminal(known.run) && run.status !== known.run.status &&
        !(known.run.status === "partial" && run.status === "succeeded");
      if (known.revision > revision || terminalChange || known.run.status === "running" && run.status === "queued") return known.run;
    }
    s.known.set(run.runId, { run, revision });
    if (terminal(run)) {
      if (s.pending === run.runId) { s.pending = null; setPendingRunId(null); }
      s.cancelled.delete(run.runId);
      setCancelling([...s.cancelled]);
    }
    return run;
  }, []);
  const refresh = useCallback(async (cursor?: string) => {
    const s = session.current;
    if (!client || !s?.alive) return;
    const { controller, current } = request(s, "history");
    const revision = ++s.revision;
    if (cursor) setLoadingMore(true); else setLoading(true);
    setError(null);
    try {
      const response = await client.call("scan.history", { limit: HISTORY_LIMIT, ...(cursor ? { cursor } : {}) }, { signal: controller.signal });
      if (!current()) return;
      const items = response.items.map(run => accept(s, run, revision));
      const missingActive = [...s.known.values()].map(item => item.run).filter(run => active(run) && !items.some(item => item.runId === run.runId));
      if (!cursor) items.unshift(...missingActive);
      setRuns(previous => cursor ? [...new Map([...previous, ...items].map(run => [run.runId, run])).values()] : items);
      setBudget(response.budget); setCursor(response.nextCursor);
    } catch (failure) { if (current()) setError(asError(failure)); }
    finally { if (current()) { setLoading(false); setLoadingMore(false); } }
  }, [client, request, accept]);
  const loadDetail = useCallback(async (runId: string) => {
    const s = session.current;
    if (!client || !s?.alive || s.selected !== runId) return;
    const { controller, current } = request(s, "detail");
    const revision = ++s.revision;
    setDetailLoading(true); setDetailError(null);
    try {
      const response = await client.call("scan.detail", { runId }, { signal: controller.signal });
      if (!current() || s.selected !== runId) return;
      if (response.run.runId !== runId) throw new RpcError("INTERNAL", scan.runNotFound);
      const run = accept(s, response.run, revision);
      setDetail({ ...response, run });
      setRuns(previous => previous.map(item => item.runId === runId ? run : item));
    } catch (failure) { if (current() && s.selected === runId) setDetailError(asError(failure)); }
    finally { if (current() && s.selected === runId) setDetailLoading(false); }
  }, [client, request, accept]);
  const status = useCallback(async (runId: string) => {
    const s = session.current;
    if (!client || !s?.alive) return;
    const { controller, current } = request(s, `status:${runId}`);
    const revision = ++s.revision;
    try {
      const result = await client.call("scan.status", { runId }, { signal: controller.signal });
      if (!current()) return;
      if (result.runId !== runId) throw new RpcError("INTERNAL", scan.runNotFound);
      const run = accept(s, result, revision);
      setRuns(previous => previous.some(item => item.runId === runId) ? previous.map(item => item.runId === runId ? run : item) : [run, ...previous]);
      setDetail(previous => previous?.run.runId === runId ? { ...previous, run } : previous);
    } catch (failure) { if (current()) setActionError(asError(failure)); }
  }, [client, request, accept]);
  const open = useCallback((runId: string) => {
    const s = session.current;
    if (!s?.alive) return;
    s.selected = runId; setSelected(runId); setDetail(null); setDetailError(null);
    void loadDetail(runId);
  }, [loadDetail]);
  const close = useCallback(() => {
    const s = session.current;
    if (s) { s.selected = null; s.controllers.get("detail")?.abort(); }
    setSelected(null); setDetail(null); setDetailError(null); setDetailLoading(false);
  }, []);

  const start = useCallback(async () => {
    const s = session.current;
    if (!client || !s?.alive || s.operations.has("start") || s.pending || [...s.known.values()].some(({ run }) => active(run))) return;
    s.operations.add("start"); setStarting(true); setActionError(null);
    const { controller, current } = request(s, "start");
    try {
      const result = await client.call("scan.start", { market: "us" }, { signal: controller.signal });
      if (!current()) return;
      s.pending = result.runId; setPendingRunId(result.runId);
      await Promise.all([status(result.runId), refresh()]);
    } catch (failure) {
      if (!current()) return;
      const rpcError = asError(failure); setActionError(rpcError);
      await refresh();
      if (!current()) return;
      // CONFLICT 的 wire 没有 runId，恢复必须读取实际历史，再查询已有运行。
      await Promise.all([...s.known.values()].filter(({ run }) => active(run)).map(({ run }) => status(run.runId)));
    } finally { s.operations.delete("start"); if (current()) setStarting(false); }
  }, [client, request, refresh, status]);
  const cancel = useCallback(async (runId: string) => {
    const s = session.current;
    if (!client || !s?.alive || s.cancelled.has(runId) || s.operations.has("cancel")) return;
    s.operations.add("cancel"); s.cancelled.add(runId); setCancelling([...s.cancelled]); setActionError(null);
    const { controller, current } = request(s, "cancel");
    try {
      await client.call("scan.cancel", { runId }, { signal: controller.signal });
      if (current()) await Promise.all([status(runId), refresh()]);
    } catch (failure) {
      if (!current()) return;
      s.cancelled.delete(runId); setCancelling([...s.cancelled]); setActionError(asError(failure));
      await Promise.all([status(runId), refresh()]);
    } finally { s.operations.delete("cancel"); }
  }, [client, request, status, refresh]);
  const retry = useCallback(async (batchId: string) => {
    const s = session.current, runId = s?.selected;
    const key = `retry:${batchId}`;
    if (!client || !s?.alive || !runId || s.operations.has(key)) return;
    s.operations.add(key); setRetrying(previous => [...previous, batchId]);
    setRetryErrors(previous => { const next = { ...previous }; delete next[batchId]; return next; });
    const { controller, current } = request(s, key);
    try {
      const batch = await client.call("scan.retryBatch", { batchId }, { signal: controller.signal, timeoutMs: RETRY_TIMEOUT_MS });
      if (!current()) return;
      if (batch.batchId !== batchId || batch.runId !== runId) throw new RpcError("INTERNAL", scan.batchMismatch);
      if (batch.status !== "succeeded") throw new RpcError("MODEL_ERROR", batch.error?.message ?? scan.retryUnconfirmed, true);
      setDetail(previous => previous?.run.runId === runId ? { ...previous, batches: previous.batches.map(item => item.batchId === batchId ? batch : item) } : previous);
      notifyToast("success", scan.retrySuccess);
    } catch (failure) {
      if (!current()) return;
      const rpcError = asError(failure);
      setRetryErrors(previous => ({ ...previous, [batchId]: rpcError }));
    } finally {
      if (current()) {
        setRetrying(previous => previous.filter(id => id !== batchId));
        setReconciling(previous => [...previous, batchId]);
        await Promise.all([loadDetail(runId), refresh(), status(runId)]);
        if (current()) setReconciling(previous => previous.filter(id => id !== batchId));
      }
      s.operations.delete(key);
    }
  }, [client, request, loadDetail, refresh, status]);

  useEffect(() => {
    const s: Session = { alive: true, controllers: new Map(), known: new Map(), revision: 0,
      operations: new Set(), selected: null, pending: null, cancelled: new Set() };
    session.current = s;
    setRuns([]); setBudget(null); setCursor(null); setSelected(null); setDetail(null);
    setError(null); setActionError(null); setDetailError(null); setRetryErrors({}); setRetrying([]); setReconciling([]);
    setProgress({}); setStarting(false); setPendingRunId(null); setCancelling([]); setLoadingMore(false);
    setLoading(Boolean(client));
    const latest = new Map<string, ScanProgress>();
    let timer: ReturnType<typeof setTimeout> | undefined, last = -Infinity;
    const flush = () => {
      if (!s.alive) return;
      timer = undefined; last = performance.now();
      const snapshot = Object.fromEntries(latest);
      latest.clear();
      setProgress(previous => ({ ...previous, ...snapshot }));
    };
    const off = client ? [
      client.subscribe("scan.progress", event => {
        const known = s.known.get(event.runId)?.run;
        if (!s.alive || event.market !== "us" || known && terminal(known)) return;
        if (!known && !s.controllers.has(`status:${event.runId}`)) {
          s.pending = event.runId; setPendingRunId(event.runId);
          void status(event.runId);
        }
        latest.set(event.runId, event);
        const remaining = PROGRESS_THROTTLE_MS - (performance.now() - last);
        if (remaining <= 0) flush(); else if (!timer) timer = setTimeout(flush, remaining);
      }),
      client.subscribe("scan.finished", result => {
        if (!s.alive || result.market !== "us" || !terminal(result)) return;
        const run = accept(s, result, ++s.revision);
        latest.delete(run.runId);
        setProgress(previous => { const next = { ...previous }; delete next[run.runId]; return next; });
        setRuns(previous => previous.some(item => item.runId === run.runId) ? previous.map(item => item.runId === run.runId ? run : item) : [run, ...previous]);
        setDetail(previous => previous?.run.runId === run.runId ? { ...previous, run } : previous);
        void refresh(); if (s.selected === run.runId) void loadDetail(run.runId);
      }),
      client.subscribe("budget.updated", value => { if (s.alive) setBudget(value); }),
    ] : [];
    const focus = () => {
      const ids = new Set([...s.known.values()].filter(({ run }) => active(run)).map(({ run }) => run.runId));
      if (s.pending) ids.add(s.pending); if (s.selected) ids.add(s.selected);
      void Promise.all([...ids].map(status));
      if (s.selected) void loadDetail(s.selected);
    };
    window.addEventListener("focus", focus);
    void refresh();
    return () => {
      s.alive = false; s.controllers.forEach(controller => controller.abort());
      off.forEach(unsubscribe => unsubscribe()); clearTimeout(timer); window.removeEventListener("focus", focus);
    };
  }, [client, refresh, loadDetail, status, accept, fixtureScope]);

  const activeRunId = pendingRunId ?? runs.find(active)?.runId ?? null;
  const control: ScanControl = { activeRunId, starting, cancelling: activeRunId !== null && cancelling.includes(activeRunId), start, cancel };
  return { runs, budget, loading, error, actionError, refresh: () => refresh(), nextCursor, loadingMore,
    loadMore: () => nextCursor ? refresh(nextCursor) : Promise.resolve(), selected, open, close,
    detail, detailLoading, detailError, refreshDetail: () => selected ? loadDetail(selected) : Promise.resolve(),
    retry, retrying, reconciling, retryErrors, progress, control };
}
