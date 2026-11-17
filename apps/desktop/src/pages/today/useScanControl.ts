import { useCallback, useEffect, useRef, useState } from "react";
import { notifyToast } from "../../app/events";
import { useAppStore } from "../../app/store";
import { today } from "../../i18n/zh-CN/today";
import { RpcError, type ParamsOfNotification, type RpcClient } from "../../rpc";
import { validFinished, validProgress } from "./state";
export const PROGRESS_MIN_MS = 500;
type ProgressValue = ParamsOfNotification<"scan.progress">;
type Session = { active: boolean; runId: string | null; ended: Set<string>; last: number;
  pending: ProgressValue | null; timer: ReturnType<typeof setTimeout> | null; start: Promise<void> | null;
  cancel: Promise<void> | null; cancelling: boolean; conflict: boolean; controllers: Set<AbortController> };
export function useScanControl(client: RpcClient, initialRunId: string | null = null) {
  const [view, setView] = useState<{ runId: string | null; progress: ProgressValue | null; starting: boolean; cancelling: boolean; conflict: boolean }>({
    runId: initialRunId, progress: null, starting: false, cancelling: false, conflict: false });
  const session = useRef<Session | null>(null);
  useEffect(() => {
    const seeded = useAppStore.getState().scanProgress;
    const current: Session = { active: true, runId: validProgress(seeded) ? seeded.runId : null, ended: new Set(),
      last: -Infinity, pending: null, timer: null, start: null, cancel: null, cancelling: false, conflict: false, controllers: new Set() };
    session.current = current;
    setView({ runId: current.runId, progress: validProgress(seeded) ? seeded : null, starting: false, cancelling: false, conflict: false });
    const commit = (progress: ProgressValue | null) => {
      current.conflict = false;
      setView(value => ({ ...value, runId: current.runId, progress, cancelling: current.cancelling, conflict: false }));
      if (useAppStore.getState().client === client) useAppStore.getState().setScanProgress(progress);
      current.last = performance.now();
    };
    const off = [client.subscribe("scan.progress", event => {
      if (!validProgress(event) || current.ended.has(event.runId) || current.runId && current.runId !== event.runId) return;
      current.runId = event.runId;
      const remaining = PROGRESS_MIN_MS - (performance.now() - current.last);
      if (remaining <= 0) { commit(event); return; }
      current.pending = event;
      if (!current.timer) current.timer = setTimeout(() => {
        current.timer = null;
        if (current.active && current.pending) { commit(current.pending); current.pending = null; }
      }, remaining);
    }), client.subscribe("scan.finished", event => {
      if (!validFinished(event)) return;
      current.ended.add(event.runId);
      if (current.runId && current.runId !== event.runId) return;
      clearTimeout(current.timer ?? undefined); current.timer = null; current.pending = null;
      current.runId = null; current.cancelling = false; commit(null);
      if (event.status === "succeeded" && useAppStore.getState().client === client) useAppStore.getState().setLastSuccessfulScanAt(event.finishedAt);
    })];
    return () => {
      current.active = false; clearTimeout(current.timer ?? undefined); current.controllers.forEach(controller => controller.abort());
      off.forEach(unsubscribe => unsubscribe());
    };
  }, [client]);
  useEffect(() => {
    const current = session.current;
    if (initialRunId && current?.active && !current.runId && !current.ended.has(initialRunId)) {
      current.runId = initialRunId;
      setView(value => ({ ...value, runId: initialRunId }));
    }
  }, [initialRunId]);
  const start = useCallback((): Promise<void> => {
    const current = session.current;
    if (!current?.active) return Promise.resolve();
    if (current.start) return current.start;
    if (current.runId || current.conflict) { notifyToast("info", today.scanConflict); return Promise.resolve(); }
    const store = useAppStore.getState(), boot = store.bootstrap.value;
    if (store.client === client && boot && (!boot.configured.jevKey || !boot.configured.secEmail || boot.offline || store.dataStatus?.offline)) {
      notifyToast("error", !boot.configured.jevKey || !boot.configured.secEmail ? today.configRequired : today.offlineScan);
      return Promise.resolve();
    }
    const controller = new AbortController(); current.controllers.add(controller);
    setView(value => ({ ...value, starting: true }));
    current.start = Promise.resolve().then(async () => {
      try {
        const result = await client.call("scan.start", { market: "us" }, { signal: controller.signal });
        if (!current.active || controller.signal.aborted || current.ended.has(result.runId)) return;
        current.runId = result.runId; setView(value => ({ ...value, runId: result.runId }));
      } catch (error) {
        if (current.active && !controller.signal.aborted) {
          const conflict = error instanceof RpcError && error.code === "CONFLICT";
          notifyToast(conflict ? "info" : "error", conflict ? today.scanConflict : error instanceof RpcError ? error.message : today.scanFailedHelp);
          if (conflict && !current.runId) {
            current.conflict = true; setView(value => ({ ...value, conflict: true }));
            try {
              const history = await client.call("scan.history", { limit: 30 }, { signal: controller.signal });
              const running = history.items.find(run => run.market === "us" && ["running", "queued"].includes(run.status));
              if (current.active && !controller.signal.aborted && running && !current.ended.has(running.runId) && !current.runId) {
                current.runId = running.runId; current.conflict = false;
                setView(value => ({ ...value, runId: running.runId, conflict: false }));
              }
            } catch { /* 后续真实进度或终态通知解除冲突，禁止轮询。 */ }
          }
        }
      } finally {
        current.start = null; current.controllers.delete(controller);
        if (current.active) setView(value => ({ ...value, starting: false }));
      }
    });
    return current.start;
  }, [client]);
  const cancel = useCallback((): Promise<void> => {
    const current = session.current;
    if (!current?.active || !current.runId || current.cancelling) return current?.cancel ?? Promise.resolve();
    const runId = current.runId, controller = new AbortController(); current.controllers.add(controller);
    current.cancelling = true; setView(value => ({ ...value, cancelling: true }));
    current.cancel = Promise.resolve().then(async () => {
      try { await client.call("scan.cancel", { runId }, { signal: controller.signal }); }
      catch (error) {
        if (current.active && !controller.signal.aborted) {
          current.cancelling = false; setView(value => ({ ...value, cancelling: false }));
          notifyToast("error", error instanceof RpcError ? error.message : today.scanFailedHelp);
        }
      } finally { current.cancel = null; current.controllers.delete(controller); }
    });
    return current.cancel;
  }, [client]);
  return { ...view, start, cancel };
}
