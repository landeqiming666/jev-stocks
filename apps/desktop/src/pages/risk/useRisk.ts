import { useCallback, useEffect, useRef, useState } from "react";
import { RpcError, type RiskResult, type RpcClient, type ResultOf } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";

type Window = RiskResult["window"]["label"];
type PriceTask = { controller: AbortController; promise: Promise<ResultOf<"prices.refresh">> };

export function useRisk(client: RpcClient | null, ready = true) {
  const [window, setWindow] = useState<Window>("1Y");
  const [result, setResult] = useState<RiskResult | null>(null);
  const [error, setError] = useState<RpcError | null>(null);
  const [loading, setLoading] = useState(false);
  const active = useRef<AbortController | null>(null);
  const prices = useRef<PriceTask | null>(null);
  const mounted = useRef(false);
  const busy = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      active.current?.abort();
      prices.current?.controller.abort();
      prices.current = null;
      busy.current = false;
    };
  }, [client]);

  const run = useCallback(async (selected: Window) => {
    if (!client || !ready || !mounted.current) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const current = () => mounted.current && active.current === controller && !controller.signal.aborted;
    busy.current = true;
    setLoading(true);
    setError(null);
    try {
      // 切窗不取消行情刷新；所有新计算等待同一刷新结果，再由最后的窗口取得展示权。
      const priceTask = prices.current;
      if (priceTask) {
        const refreshed = await priceTask.promise;
        if (!current()) return;
        if (refreshed.failed.length) throw new RpcError("SOURCE_UNAVAILABLE", risk.partialRefresh(
          refreshed.failed.map(item => `${item.instrumentId}（${item.error.message}）`).join("、")), true);
      }
      if (!current()) return;
      const value = await client.call("risk.compute", { scope: "holdings", window: selected, currency: "USD" },
        { signal: controller.signal });
      if (current()) setResult(value);
    } catch (cause) {
      if (current()) setError(cause instanceof RpcError ? cause : new RpcError("INTERNAL", risk.loadFailed));
    } finally {
      if (current()) { busy.current = false; setLoading(false); }
    }
  }, [client, ready]);

  useEffect(() => {
    void run(window);
    return () => { active.current?.abort(); };
  }, [run, window]);

  const refresh = useCallback(async () => {
    if (!busy.current) await run(window);
  }, [run, window]);

  const refreshPrices = useCallback(async () => {
    if (!client || !ready || !mounted.current || busy.current) return;
    active.current?.abort();
    const controller = new AbortController();
    const task: PriceTask = { controller, promise: client.call("prices.refresh", {}, { signal: controller.signal }) };
    prices.current = task;
    try { await run(window); }
    finally { if (prices.current === task) prices.current = null; }
  }, [client, ready, run, window]);

  return { result, loading, error, window, setWindow, refresh, refreshPrices };
}
