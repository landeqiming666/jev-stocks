import { common } from "../i18n/zh-CN";
import { RpcError, type Bootstrap, type RpcClient } from "../rpc";
import { initialState, useAppStore } from "./store";

export const BOOTSTRAP_TIMEOUT_MS = 30_000;
export async function bootstrapApp(client: RpcClient, signal?: AbortSignal): Promise<Bootstrap> {
  const controller = new AbortController();
  const deadline = performance.now() + BOOTSTRAP_TIMEOUT_MS;
  let timedOut = false;
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, BOOTSTRAP_TIMEOUT_MS);
  const options = () => ({ signal: controller.signal, timeoutMs: Math.max(0, deadline - performance.now()) });
  try {
    await client.whenReady(options());
    if (controller.signal.aborted) throw new RpcError("CANCELLED", common.startFailed);
    const value = await client.call("app.bootstrap", {}, options());
    if (controller.signal.aborted || performance.now() >= deadline) {
      throw new RpcError(timedOut ? "TIMEOUT" : "CANCELLED", common.startTimeout);
    }
    if (typeof value.protocolVersion !== "string" || !value.protocolVersion.startsWith("1.")) {
      throw new RpcError("INTERNAL", common.protocolMismatch, false,
        { reason: "PROTOCOL_MISMATCH", messageKey: "common.protocolMismatch" });
    }
    return value;
  } catch (error) {
    if (timedOut || (error instanceof RpcError && error.code === "TIMEOUT")) {
      throw new RpcError("TIMEOUT", common.startTimeout, true, { messageKey: "common.startTimeout" });
    }
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}

export function startApp(client: RpcClient): () => void {
  const controller = new AbortController();
  const off: (() => void)[] = [];
  const current = () => !controller.signal.aborted && useAppStore.getState().client === client;
  useAppStore.setState({ ...initialState(), client, bootstrap: { status: "starting", value: null, error: null } });
  void bootstrapApp(client, controller.signal).then(value => {
    if (!current()) return;
    document.documentElement.dataset.platform = value.platform;
    useAppStore.setState({ bootstrap: { status: "ready", value, error: null } });
    off.push(client.subscribe("engine.changed", event => {
      if (!current()) return;
      useAppStore.setState(state => ({
        bootstrap: { ...state.bootstrap, value: state.bootstrap.value && {
          ...state.bootstrap.value, engine: { ...state.bootstrap.value.engine, active: event.to },
        } },
        dataStatus: state.dataStatus && { ...state.dataStatus, engine: {
          ...state.dataStatus.engine, active: event.to, state: !event.to ? "unconfigured" :
            event.from === "jevdb" && event.to === "jev_direct" ? "degraded" : "ok",
        } },
        ui: { ...state.ui, engineNotice: true },
      }));
    }), client.subscribe("source.degraded", () => {
      if (current()) useAppStore.setState(state => ({ ui: { ...state.ui, sourceDegraded: true } }));
    }), client.subscribe("budget.updated", budget => {
      if (current()) useAppStore.getState().setBudget(budget);
    }));
  }).catch(error => {
    if (!current()) return;
    off.splice(0).forEach(unsubscribe => unsubscribe());
    client.dispose();
    useAppStore.setState({ client: null, bootstrap: { status: "failed", value: null,
      error: error instanceof RpcError ? error : new RpcError("INTERNAL", common.startFailed) } });
  });
  return () => {
    controller.abort();
    off.splice(0).forEach(unsubscribe => unsubscribe());
    client.dispose();
    if (useAppStore.getState().client === client) useAppStore.setState({ client: null });
  };
}
