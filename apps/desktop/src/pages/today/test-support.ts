import { vi } from "vitest";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import type { Bootstrap, DecisionDetail, Inbox, MethodName, NotificationName, RpcClient } from "../../rpc";
import pending from "./__fixtures__/inbox.json";
import overturn from "./__fixtures__/decision-overturn.json";

export function example<T>(method: MethodName, name: string): T {
  const entry = (MOCK_EXAMPLES[method] as readonly { name: string; result?: unknown }[]).find(e => e.name === name);
  if (!entry || !("result" in entry)) throw new Error(`Missing fixture ${method}/${name}`);
  return structuredClone(entry.result) as T;
}
export const pendingInbox = () => structuredClone(pending) as Inbox;
export const overturnDetail = () => structuredClone(overturn) as DecisionDetail;
export const readyBoot = () => example<Bootstrap>("app.bootstrap", "ready");
export function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
export function testClient(initial = pendingInbox(), detail = overturnDetail()) {
  let inbox = initial;
  const handlers = new Map<string, Set<(value: unknown) => void>>();
  const call = vi.fn(async (method: string, params: Record<string, unknown>) => {
    if (method === "inbox.list") return structuredClone(inbox);
    if (method === "decision.get") return structuredClone(detail);
    if (method === "scan.history") return example("scan.history", "default");
    if (method === "scan.start") return example("scan.start", "ok");
    if (method === "scan.cancel") return { ok: true };
    const item = [...inbox.items, ...inbox.uncertain, ...inbox.processed].find(d => d.decisionId === params.decisionId);
    if (!item) throw new Error(`Unknown decision ${params.decisionId}`);
    return { ...item, action: { action: method === "decision.reopen" ? "reopen" : params.action,
      note: params.note ?? null, actedAt: readyBoot().now } };
  });
  const client = {
    call, status: () => "ready", whenReady: async () => {}, dispose: vi.fn(),
    subscribe: (name: string, handler: (value: unknown) => void) => {
      const group = handlers.get(name) ?? new Set(); group.add(handler); handlers.set(name, group);
      return () => { group.delete(handler); };
    },
  } as unknown as RpcClient;
  return { client, call, handlers, setInbox: (value: Inbox) => { inbox = value; },
    emit: (name: NotificationName, value: unknown) => handlers.get(name)?.forEach(handler => handler(value)) };
}
