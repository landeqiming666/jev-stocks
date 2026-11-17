import { vi } from "vitest";
import type { RpcClient, ResultOf, ParamsOfNotification, NotificationName } from "../../rpc";
import history from "./__fixtures__/history.json";
import detail from "./__fixtures__/detail.json";

export const historyFixture = history as ResultOf<"scan.history">;
export const detailFixture = detail as ResultOf<"scan.detail">;
export function testClient() {
  const listeners = new Map<string, Set<(value: never) => void>>();
  const call = vi.fn(async (method: string, params?: unknown): Promise<unknown> => {
    if (method === "scan.history") return structuredClone(historyFixture);
    if (method === "scan.detail") return structuredClone(detailFixture);
    if (method === "scan.status") return structuredClone(historyFixture.items.find(run => run.runId === (params as { runId: string }).runId));
    if (method === "scan.start") return { runId: historyFixture.items[0]!.runId };
    if (method === "scan.cancel") return { ok: true };
    if (method === "scan.retryBatch") return { ...detailFixture.batches[2], status: "succeeded" };
    throw new Error(method);
  });
  const client = {
    call, status: () => "ready", whenReady: async () => {}, dispose: vi.fn(),
    subscribe(name: string, listener: (value: never) => void) {
      const group = listeners.get(name) ?? new Set();
      group.add(listener); listeners.set(name, group);
      return () => { group.delete(listener); };
    },
  } as unknown as RpcClient;
  return { client, call, listeners,
    emit<N extends NotificationName>(name: N, value: ParamsOfNotification<N>) {
      listeners.get(name)?.forEach(listener => listener(value as never));
    },
  };
}
