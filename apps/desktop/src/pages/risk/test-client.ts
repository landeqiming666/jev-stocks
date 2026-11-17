import { vi } from "vitest";
import type { RpcClient } from "../../rpc";
import { ok } from "./__fixtures__/results";

export function clientFixture() {
  const call = vi.fn().mockResolvedValue(ok);
  const client: RpcClient = {
    call, status: () => "ready", whenReady: async () => {},
    subscribe: () => () => {}, dispose: vi.fn(),
  };
  return { client, call };
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
