import { expect, test, vi } from "vitest";
import type { RpcClient } from "../rpc/client";
import { subscribeCoreStatus } from "./core-status";

const tick = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
const client = (status: RpcClient["status"]) => ({ status } as RpcClient);

test("listener_registers_before_existing_client_snapshot_without_rpc_call", async () => {
  const order: string[] = [], handler = vi.fn();
  const off = subscribeCoreStatus(client(() => { order.push("snapshot"); return "failed"; }), handler,
    async () => { order.push("listen"); return () => { order.push("cleanup"); }; });
  await tick();
  expect(order).toEqual(["listen", "snapshot"]);
  expect(handler).toHaveBeenCalledWith("failed");
  off();
  expect(order).toEqual(["listen", "snapshot", "cleanup"]);
});

test("event_during_listener_registration_wins_over_stale_ready_snapshot", async () => {
  const snapshot = vi.fn(() => "ready" as const), handler = vi.fn();
  const off = subscribeCoreStatus(client(snapshot), handler, async emit => {
    emit({ state: "restarting", attempt: 1 });
    return () => {};
  });
  await tick();
  expect(handler.mock.calls).toEqual([["restarting"]]);
  expect(snapshot).not.toHaveBeenCalled();
  off();
});

test("late_registration_cleanup_ignores_events_after_unmount_and_validates_payload", async () => {
  const release = vi.fn(), handler = vi.fn();
  let emit: (payload: unknown) => void = () => {};
  let resolve: (off: () => void) => void = () => {};
  const off = subscribeCoreStatus(client(() => "ready"), handler, callback => {
    emit = callback;
    return new Promise(done => { resolve = done; });
  });
  await tick();
  for (const payload of [{ state: "private", attempt: 0 }, { state: "failed", attempt: -1 }, { state: "ready" }, null]) emit(payload);
  expect(handler).not.toHaveBeenCalled();
  off(); resolve(release); await tick();
  emit({ state: "failed", attempt: 0 });
  expect(release).toHaveBeenCalledTimes(1);
  expect(handler).not.toHaveBeenCalled();
});

test("listener_failure_uses_existing_mock_client_status_without_tauri", async () => {
  const handler = vi.fn();
  const off = subscribeCoreStatus(client(() => "restarting"), handler, async () => { throw new Error("private-secret"); });
  await tick();
  expect(handler).toHaveBeenCalledWith("restarting");
  off();
});
