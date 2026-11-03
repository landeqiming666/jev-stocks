import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { METHOD_TIMEOUTS, NOTIFICATION_NAMES } from "./generated/methods";
import type { MethodName, NotificationName, ParamsOf, ParamsOfNotification, ResultOf } from "./generated/methods";
import { isObject, RpcError, RPC_MESSAGES } from "./errors";

export const DEFAULT_TIMEOUT_MS = 30_000;
export const CONNECTION_TIMEOUT_MS = 20_000;
export const EXPORT_TIMEOUT_MS = 60_000;
export const ID_PREFIX = "r-";
export type CoreStatus = "starting" | "ready" | "restarting" | "failed";
export type CallOptions = { timeoutMs?: number; signal?: AbortSignal };
export interface RpcClient {
  call<M extends MethodName>(method: M, params: ParamsOf<M>, options?: CallOptions): Promise<ResultOf<M>>;
  subscribe<N extends NotificationName>(name: N, handler: (params: ParamsOfNotification<N>) => void): () => void;
  status(): CoreStatus;
  whenReady(options?: CallOptions): Promise<void>;
  dispose(): void;
}
export interface RpcTransport {
  invoke(command: string, args?: { line: string }): Promise<unknown>;
  listen(name: string, handler: (event: { payload: unknown }) => void): Promise<() => void>;
}
export type RpcClientOptions = { transport?: RpcTransport; warn?: (message: string) => void };
type Pending = { finish: (error?: RpcError, result?: unknown) => void; sent: boolean };
let counter = 0;

export function createRpcClient(options: RpcClientOptions = {}): RpcClient {
  const transport: RpcTransport = options.transport ?? { invoke, listen };
  const pending = new Map<string, Pending>();
  const handlers = new Map<string, Set<(params: unknown) => void>>();
  const statusHandlers = new Set<() => void>();
  const unlisteners = new Set<() => void>();
  const warned = new Set<string>();
  let state: CoreStatus = "starting", revision = 0, disposed = false, initialized = false;
  function warn(category: string) {
    if (!warned.has(category)) { warned.add(category); (options.warn ?? console.warn)("rpc: " + category); }
  }
  function rejectAll(message: string) {
    for (const item of [...pending.values()]) item.finish(new RpcError("INTERNAL", message));
  }
  async function send(command: string, args?: { line: string }) {
    return args ? transport.invoke(command, args) : transport.invoke(command);
  }
  function release(off: () => void) {
    try { off(); } catch { warn("listener cleanup failed"); }
  }
  function setStatus(value: unknown) {
    if (!isObject(value) || typeof value.state !== "string" || !["starting", "ready", "restarting", "failed"].includes(value.state) ||
        typeof value.attempt !== "number" || !Number.isInteger(value.attempt) || value.attempt < 0) {
      warn("invalid status"); return false;
    }
    state = value.state as CoreStatus;
    if (state === "restarting" || state === "failed") rejectAll(RPC_MESSAGES.disconnected);
    for (const handler of [...statusHandlers]) handler();
    return true;
  }
  function message(payload: unknown) {
    if (disposed) return;
    let value: unknown;
    try { value = typeof payload === "string" ? JSON.parse(payload) : null; }
    catch { warn("invalid message"); return; }
    if (!isObject(value) || value.jsonrpc !== "2.0") { warn("invalid message"); return; }
    if (Object.hasOwn(value, "id")) {
      if (typeof value.id !== "string" || Object.hasOwn(value, "result") === Object.hasOwn(value, "error")) {
        warn("invalid response"); return;
      }
      const item = pending.get(value.id);
      if (!item) { warn("unknown response id"); return; }
      item.finish(Object.hasOwn(value, "error") ? RpcError.fromWire(value.error) : undefined, value.result);
    } else if (typeof value.method === "string" && NOTIFICATION_NAMES.some(n => n === value.method) && isObject(value.params)) {
      for (const handler of [...(handlers.get(value.method) ?? [])]) {
        try { handler(value.params); } catch { warn("notification handler failed"); }
      }
    } else { warn("invalid or unknown notification"); }
  }
  async function register(name: string, handler: (event: { payload: unknown }) => void) {
    const off = await transport.listen(name, handler);
    if (disposed) release(off); else unlisteners.add(off);
  }
  const setup = (async () => {
    try {
      // 状态先监听；事件版本使查询期间到达的新状态优先于旧快照。
      await Promise.all([
        register("core://status", event => { if (!disposed && setStatus(event.payload)) revision++; }),
        register("core://message", event => message(event.payload)),
      ]);
      if (disposed) return;
      const snapshotRevision = revision;
      const snapshot = await send("core_status");
      if (!disposed && revision === snapshotRevision) setStatus(snapshot);
      initialized = true;
      for (const handler of [...statusHandlers]) handler();
    } catch {
      if (!disposed) {
        disposed = true; state = "failed";
        rejectAll(RPC_MESSAGES.disconnected);
        for (const off of unlisteners) release(off);
        unlisteners.clear(); handlers.clear();
        for (const handler of [...statusHandlers]) handler();
        statusHandlers.clear();
      }
    }
  })();
  function sendCancel(id: string, item: Pending) {
    if (item.sent) void send("rpc_send", { line: JSON.stringify({ jsonrpc: "2.0", method: "$/cancel", params: { id } }) })
      .catch(() => warn("cancel send failed"));
  }
  function timeout(method: string, provided?: number) {
    return provided ?? (method === "settings.testConnection" ? CONNECTION_TIMEOUT_MS :
      method.toLowerCase().includes("export") ? EXPORT_TIMEOUT_MS : DEFAULT_TIMEOUT_MS);
  }
  return {
    status: () => state,
    call<M extends MethodName>(method: M, params: ParamsOf<M>, callOptions: CallOptions = {}): Promise<ResultOf<M>> {
      if (!Object.hasOwn(METHOD_TIMEOUTS, method)) return Promise.reject(new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid, false, { reason: "UNKNOWN_METHOD" }));
      if (callOptions.signal?.aborted) return Promise.reject(new RpcError("CANCELLED", RPC_MESSAGES.cancelled));
      const ms = timeout(method, callOptions.timeoutMs);
      if (!Number.isFinite(ms) || ms < 0) return Promise.reject(new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid));
      const hex = [...crypto.getRandomValues(new Uint8Array(4))].map(n => n.toString(16).padStart(2, "0")).join("");
      const id = ID_PREFIX + ++counter + "-" + hex;
      return new Promise((resolve, reject) => {
        const finish = (error?: RpcError, result?: unknown) => {
          if (!pending.delete(id)) return;
          clearTimeout(timer); callOptions.signal?.removeEventListener("abort", abort);
          if (error) reject(error); else resolve(result as ResultOf<M>);
        };
        const item: Pending = { finish, sent: false };
        const abort = () => { finish(new RpcError("CANCELLED", RPC_MESSAGES.cancelled)); sendCancel(id, item); };
        const timer = setTimeout(() => { finish(new RpcError("TIMEOUT", RPC_MESSAGES.timeout)); sendCancel(id, item); }, ms);
        pending.set(id, item);
        callOptions.signal?.addEventListener("abort", abort, { once: true });
        if (callOptions.signal?.aborted) { abort(); return; }
        void setup.then(() => {
          if (!pending.has(id)) return;
          if (disposed || state !== "ready") { finish(new RpcError("INTERNAL", RPC_MESSAGES.notReady)); return; }
          let line: string;
          try { line = JSON.stringify({ jsonrpc: "2.0", id, method, params }); }
          catch { finish(new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid)); return; }
          item.sent = true;
          void send("rpc_send", { line }).catch(() => finish(new RpcError("INTERNAL", RPC_MESSAGES.disconnected)));
        });
      });
    },
    subscribe<N extends NotificationName>(name: N, handler: (params: ParamsOfNotification<N>) => void) {
      if (disposed) return () => {};
      // 每次订阅独立包装，相同回调也能独立退订。
      const wrapped = (params: unknown) => handler(params as ParamsOfNotification<N>);
      const group = handlers.get(name) ?? new Set(); group.add(wrapped); handlers.set(name, group);
      return () => { group.delete(wrapped); if (!group.size) handlers.delete(name); };
    },
    whenReady(readyOptions: CallOptions = {}) {
      if (readyOptions.signal?.aborted) return Promise.reject(new RpcError("CANCELLED", RPC_MESSAGES.cancelled));
      const ms = readyOptions.timeoutMs ?? DEFAULT_TIMEOUT_MS;
      if (!Number.isFinite(ms) || ms < 0) return Promise.reject(new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid));
      return new Promise<void>((resolve, reject) => {
        const finish = (error?: RpcError) => {
          clearTimeout(timer); statusHandlers.delete(check);
          readyOptions.signal?.removeEventListener("abort", abort);
          if (error) reject(error); else resolve();
        };
        const check = () => {
          if (disposed || state === "failed") finish(new RpcError("INTERNAL", RPC_MESSAGES.disconnected));
          else if (initialized && state === "ready") finish();
        };
        const abort = () => finish(new RpcError("CANCELLED", RPC_MESSAGES.cancelled));
        const timer = setTimeout(() => finish(new RpcError("TIMEOUT", RPC_MESSAGES.timeout)), ms);
        statusHandlers.add(check); readyOptions.signal?.addEventListener("abort", abort, { once: true });
        if (readyOptions.signal?.aborted) abort(); else check();
      });
    },
    dispose() {
      disposed = true; state = "failed"; rejectAll(RPC_MESSAGES.disposed);
      for (const off of unlisteners) release(off); unlisteners.clear(); handlers.clear();
      for (const handler of [...statusHandlers]) handler(); statusHandlers.clear();
    },
  };
}
