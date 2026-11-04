import { listen } from "@tauri-apps/api/event";
import type { CoreStatus, RpcClient } from "../rpc/client";
import { ownValue } from "./errors";

export type CoreStatusListener = (handler: (payload: unknown) => void) => Promise<() => void>;
export const listenCoreStatus: CoreStatusListener = async handler => {
  if (import.meta.env.VITE_RPC === "mock") return () => {};
  return listen("core://status", event => handler(event.payload));
};
const valid = (state: unknown): state is CoreStatus => typeof state === "string" &&
  ["starting", "restarting", "ready", "failed"].includes(state);

export function subscribeCoreStatus(client: RpcClient, handler: (state: CoreStatus) => void,
  listener: CoreStatusListener = listenCoreStatus): () => void {
  let active = true, revision = 0;
  let release: (() => void) | undefined;
  const initialRevision = revision;
  // listener 安装期间的新事件必须胜过旧 client.status 快照；不调用 core_status、不另建 client。
  void Promise.resolve().then(() => listener(payload => {
    const state = ownValue(payload, "state"), attempt = ownValue(payload, "attempt");
    if (!active || !valid(state) || typeof attempt !== "number" || !Number.isInteger(attempt) || attempt < 0) return;
    revision++;
    handler(state);
  })).then(off => {
    if (!active) { off(); return; }
    release = off;
    if (revision === initialRevision) {
      const state = client.status();
      if (valid(state)) handler(state);
    }
  }).catch(() => {
    if (active && revision === initialRevision) {
      try { const state = client.status(); if (valid(state)) handler(state); } catch { handler("failed"); }
    }
  });
  return () => {
    if (!active) return;
    active = false;
    try { release?.(); } catch { /* 清理失败也不能打印异常原文。 */ }
  };
}
