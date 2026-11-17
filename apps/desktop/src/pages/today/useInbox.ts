import { useCallback, useEffect, useRef, useState } from "react";
import { notifyToast, REFRESH_EVENT } from "../../app/events";
import { useAppStore } from "../../app/store";
import { today } from "../../i18n/zh-CN/today";
import { RpcError, type ActionType, type DecisionSummary, type Inbox, type RpcClient } from "../../rpc";
import { placeDecision, validFinished, validInboxUpdate } from "./state";

type Snapshot = { state: "loading" | "ready" | "error"; inbox: Inbox | null; error: RpcError | null };
type Mutation = { promise: Promise<void>; optimistic: DecisionSummary };
type Session = { active: boolean; request: number; load: AbortController | null; controllers: Set<AbortController>; mutations: Map<string, Mutation> };
export function useInbox(client: RpcClient) {
  const [snapshot, setSnapshot] = useState<Snapshot>({ state: "loading", inbox: null, error: null });
  const value = useRef<Inbox | null>(null), session = useRef<Session | null>(null);
  const publish = useCallback((inbox: Inbox, metadata = false) => {
    value.current = inbox; setSnapshot({ state: "ready", inbox, error: null });
    if (metadata && useAppStore.getState().client === client) {
      useAppStore.getState().setDataStatus(inbox.dataStatus, inbox.asOf);
      if (inbox.lastScan?.status === "succeeded" && inbox.lastScan.finishedAt) useAppStore.getState().setLastSuccessfulScanAt(inbox.lastScan.finishedAt);
    }
  }, [client]);
  const refresh = useCallback(async () => {
    const current = session.current;
    if (!current?.active) return;
    current.load?.abort();
    const controller = new AbortController(), request = ++current.request;
    current.load = controller;
    try {
      let inbox = await client.call("inbox.list", {}, { signal: controller.signal });
      if (!current.active || controller.signal.aborted || request !== current.request) return;
      // 通知刷新期间保留逐条乐观操作；操作完成后废弃旧快照，避免覆盖写入。
      for (const mutation of current.mutations.values()) inbox = placeDecision(inbox, mutation.optimistic);
      publish(inbox, true);
    } catch (error) {
      if (!current.active || controller.signal.aborted || request !== current.request) return;
      const rpcError = error instanceof RpcError ? error : new RpcError("INTERNAL", today.loadFailed);
      setSnapshot({ state: "error", inbox: value.current, error: rpcError });
    }
  }, [client, publish]);
  useEffect(() => {
    const current: Session = { active: true, request: 0, load: null, controllers: new Set(), mutations: new Map() };
    session.current = current; value.current = null;
    setSnapshot({ state: "loading", inbox: null, error: null });
    void refresh();
    const off = [client.subscribe("inbox.updated", event => { if (validInboxUpdate(event)) void refresh(); }),
      client.subscribe("scan.finished", event => { if (validFinished(event)) void refresh(); })];
    const focus = () => { void refresh(); };
    const requested = (event: Event) => {
      const scope = (event as CustomEvent<{ scope?: string }>).detail?.scope;
      if (!scope || scope === "today" || scope === "inbox") void refresh();
    };
    window.addEventListener("focus", focus); window.addEventListener(REFRESH_EVENT, requested);
    return () => {
      current.active = false; current.load?.abort(); current.controllers.forEach(controller => controller.abort());
      off.forEach(unsubscribe => unsubscribe());
      window.removeEventListener("focus", focus); window.removeEventListener(REFRESH_EVENT, requested);
    };
  }, [client, refresh]);
  const mutate = useCallback((id: string, action: ActionType | "reopen", note?: string): Promise<void> => {
    const current = session.current, inbox = value.current;
    if (!current?.active || !inbox) return Promise.reject(new RpcError("NOT_FOUND", today.decisionNotFound));
    const existing = current.mutations.get(id);
    if (existing) return existing.promise;
    const group = (["items", "uncertain", "processed"] as const).find(key => inbox[key].some(d => d.decisionId === id));
    if (!group) return Promise.reject(new RpcError("NOT_FOUND", today.decisionNotFound));
    const index = inbox[group].findIndex(d => d.decisionId === id), original = inbox[group][index]!;
    const normalized = note?.trim() || null;
    if (Array.from(normalized ?? "").length > 200) return Promise.reject(new RpcError("INVALID_ARGUMENT", today.noteTooLong));
    const optimistic = { ...original, action: { action, note: normalized, actedAt: inbox.asOf } };
    const controller = new AbortController(); current.controllers.add(controller);
    ++current.request; current.load?.abort();
    publish(placeDecision(inbox, optimistic));
    const promise = Promise.resolve().then(async () => {
      try {
        const result = action === "reopen" ? await client.call("decision.reopen", { decisionId: id }, { signal: controller.signal }) :
          await client.call("decision.act", { decisionId: id, action, note: normalized }, { signal: controller.signal });
        if (!current.active || controller.signal.aborted) return;
        ++current.request; current.load?.abort();
        publish(placeDecision(value.current!, result));
      } catch (error) {
        if (!current.active || controller.signal.aborted) return;
        ++current.request; current.load?.abort();
        publish(placeDecision(value.current!, original, group, index));
        notifyToast("error", error instanceof RpcError ? error.message : today.actionFailed);
        throw error;
      } finally { current.mutations.delete(id); current.controllers.delete(controller); }
    });
    current.mutations.set(id, { promise, optimistic });
    return promise;
  }, [client, publish]);
  return { ...snapshot, refresh, act: useCallback((id: string, action: ActionType, note?: string) => mutate(id, action, note), [mutate]),
    reopen: useCallback((id: string) => mutate(id, "reopen"), [mutate]) };
}
