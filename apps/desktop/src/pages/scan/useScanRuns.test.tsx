import { StrictMode, type ReactNode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { createMockRpcClient, RpcError, type ScanRun, type CallOptions } from "../../rpc";
import { useScanRuns } from "./useScanRuns";
import { detailFixture, historyFixture, testClient } from "./test-support";

afterEach(() => { cleanup(); vi.useRealTimers(); });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const running = { ...historyFixture.items[0]!, status: "running" as const, finishedAt: null };
const progress = { runId: running.runId, market: "us" as const, stage: "decide" as const, done: 1, total: 17, message: "synthetic progress" };
const mounted = (rpc: ReturnType<typeof testClient>) => renderHook(() => useScanRuns(rpc.client));

it("drops_old_history_and_aborts_superseded_request", async () => {
  const rpc = testClient(), first = deferred<unknown>();
  rpc.call.mockImplementationOnce(() => first.promise);
  const { result } = mounted(rpc);
  await act(async () => { await result.current.refresh(); });
  const options = (rpc.call.mock.calls as unknown[][])[0]![2] as CallOptions;
  expect(options.signal?.aborted).toBe(true);
  await act(async () => { first.resolve({ ...historyFixture, items: [] }); });
  expect(result.current.runs.length).toBe(4);
});

it("strictmode_resubscribes_once_aborts_requests_and_preserves_public_client", async () => {
  const rpc = testClient();
  const { result, unmount } = renderHook(() => useScanRuns(rpc.client), {
    wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect([...rpc.listeners.values()].map(group => group.size)).toEqual([1, 1, 1]);
  unmount();
  expect([...rpc.listeners.values()].every(group => group.size === 0)).toBe(true);
  expect((rpc.call.mock.calls as unknown[][]).every(call => (call[2] as CallOptions).signal?.aborted)).toBe(true);
  expect(rpc.client.dispose).not.toHaveBeenCalled();
});

it("drops_old_detail_when_switching_rows_and_closing", async () => {
  const rpc = testClient(), first = deferred<unknown>();
  rpc.call.mockImplementation(async method => method === "scan.history" ? historyFixture : first.promise);
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.open(historyFixture.items[0]!.runId));
  rpc.call.mockImplementation(async method => method === "scan.history" ? historyFixture : detailFixture);
  act(() => result.current.open(detailFixture.run.runId));
  await waitFor(() => expect(result.current.detail?.run.runId).toBe(detailFixture.run.runId));
  await act(async () => { first.resolve({ run: historyFixture.items[0], batches: [] }); });
  expect(result.current.detail?.run.runId).toBe(detailFixture.run.runId);
  act(() => result.current.close());
  expect(result.current.selected).toBeNull();
});

it("coalesces_progress_at_500ms_and_finished_refresh_cannot_restore_running", async () => {
  vi.useFakeTimers();
  const rpc = testClient();
  rpc.call.mockResolvedValue({ ...historyFixture, items: [running] });
  const { result } = mounted(rpc);
  await act(async () => {});
  act(() => rpc.emit("scan.progress", progress));
  expect(result.current.progress[running.runId]?.done).toBe(1);
  act(() => {
    rpc.emit("scan.progress", { ...progress, done: 3 });
    rpc.emit("scan.progress", { ...progress, done: 9 });
    vi.advanceTimersByTime(499);
  });
  expect(result.current.progress[running.runId]?.done).toBe(1);
  act(() => vi.advanceTimersByTime(1));
  expect(result.current.progress[running.runId]?.done).toBe(9);
  await act(async () => {
    rpc.emit("scan.progress", { ...progress, done: 17 });
    rpc.emit("scan.finished", historyFixture.items[0]!);
    vi.advanceTimersByTime(500);
  });
  expect(result.current.runs[0]?.status).toBe("succeeded");
  expect(result.current.progress[running.runId]).toBeUndefined();
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.history").length).toBe(2);
});

it("start_is_singleflight_and_conflict_recovers_real_queued_run_id", async () => {
  const rpc = testClient(), start = deferred<unknown>();
  const queued = { ...running, status: "queued" as const };
  let historyCalls = 0;
  rpc.call.mockImplementation(async method => {
    if (method === "scan.history") return { ...historyFixture, items: ++historyCalls === 1 ? [] : [queued] };
    if (method === "scan.start") { await start.promise; throw new RpcError("CONFLICT", "synthetic conflict"); }
    return queued;
  });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  let operation!: Promise<void>;
  act(() => { operation = result.current.control.start(); void result.current.control.start(); });
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.start").length).toBe(1);
  await act(async () => { start.resolve({}); await operation; });
  expect(result.current.control.activeRunId).toBe(queued.runId);
  expect(rpc.call.mock.calls.find(([m]) => m === "scan.status")?.[1]).toEqual({ runId: queued.runId });
  await act(async () => { await result.current.control.start(); });
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.start").length).toBe(1);
});

it("start_recovers_status_immediately_without_fabricated_stats", async () => {
  const rpc = testClient();
  let hasStarted = false;
  rpc.call.mockImplementation(async method => {
    if (method === "scan.start") { hasStarted = true; return { runId: running.runId }; }
    if (method === "scan.history") return { ...historyFixture, items: hasStarted ? [running] : [] };
    return running;
  });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { await result.current.control.start(); });
  expect(result.current.control.activeRunId).toBe(running.runId);
  expect(result.current.runs[0]?.stats).toEqual(running.stats);
});

it("cancel_ack_waits_for_terminal_and_duplicate_cancel_is_suppressed", async () => {
  const rpc = testClient();
  rpc.call.mockImplementation(async method => method === "scan.history" ? { ...historyFixture, items: [running] } : method === "scan.status" ? running : { ok: true });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { await Promise.all([result.current.control.cancel(running.runId), result.current.control.cancel(running.runId)]); });
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.cancel").length).toBe(1);
  expect(result.current.control.cancelling).toBe(true);
  expect(result.current.control.activeRunId).toBe(running.runId);
  await act(async () => { rpc.emit("scan.finished", { ...historyFixture.items[0]!, status: "cancelled" }); });
  expect(result.current.runs[0]?.status).toBe("cancelled");
  expect(result.current.control.activeRunId).toBeNull();
});

it("focus_queries_selected_and_active_status_without_polling", async () => {
  vi.useFakeTimers();
  const rpc = testClient();
  rpc.call.mockImplementation(async method => method === "scan.history" ? { ...historyFixture, items: [running] } : method === "scan.detail" ? detailFixture : running);
  const { result } = mounted(rpc);
  await act(async () => {});
  act(() => result.current.open(detailFixture.run.runId));
  await act(async () => {});
  act(() => vi.advanceTimersByTime(10_000));
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.status").length).toBe(0);
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  const ids = rpc.call.mock.calls.filter(([m]) => m === "scan.status").map(([, params]) => (params as { runId: string }).runId);
  expect(new Set(ids)).toEqual(new Set([running.runId, detailFixture.run.runId]));
});

it("history_pagination_passes_cursor_and_deduplicates_wire_runs", async () => {
  const rpc = testClient();
  rpc.call.mockResolvedValueOnce({ ...historyFixture, items: historyFixture.items.slice(0, 2), nextCursor: "synthetic-cursor" });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { await result.current.loadMore(); });
  expect(rpc.call.mock.calls[1]?.[1]).toEqual({ limit: 50, cursor: "synthetic-cursor" });
  expect(result.current.runs.length).toBe(4);
});

it("retry_failure_and_timeout_refresh_actual_detail_and_preserve_specific_error", async () => {
  const rpc = testClient();
  const read = rpc.call.getMockImplementation()!;
  rpc.call.mockImplementation(async (method, params) => {
    if (method === "scan.retryBatch") throw new RpcError("TIMEOUT", "synthetic retry deadline", true);
    return read(method, params);
  });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.open(detailFixture.run.runId));
  await waitFor(() => expect(result.current.detail).not.toBeNull());
  await act(async () => { await result.current.retry(detailFixture.batches[2]!.batchId); });
  const calls = rpc.call.mock.calls as unknown[][];
  expect((calls.find(([m]) => m === "scan.retryBatch")?.[2] as CallOptions).timeoutMs).toBe(60_000);
  expect(calls.filter(([m]) => m === "scan.detail").length).toBe(2);
  expect(result.current.detail?.batches[2]?.status).toBe("failed");
  expect(result.current.retryErrors[detailFixture.batches[2]!.batchId]?.message).toBe("synthetic retry deadline");
});

it("real_rpc_retry_deadline_aborts_at_60_seconds_and_refreshes", async () => {
  vi.useFakeTimers();
  const client = createMockRpcClient({ scenario: "scan.detail", warn: () => {} });
  client.setExample("scan.retryBatch", "ok");
  client.setExample("scan.status", "done");
  await act(async () => { await client.whenReady(); });
  const { result, unmount } = renderHook(() => useScanRuns(client));
  await act(async () => {});
  act(() => result.current.open(detailFixture.run.runId));
  await act(async () => {});
  client.setDelay(61_000);
  let operation!: Promise<void>;
  act(() => { operation = result.current.retry(detailFixture.batches[2]!.batchId); });
  await act(async () => {});
  client.setDelay(0);
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); await operation; });
  expect(result.current.retryErrors[detailFixture.batches[2]!.batchId]?.code).toBe("TIMEOUT");
  expect(result.current.retrying).toEqual([]);
  expect(result.current.detail?.batches[2]?.status).toBe("failed");
  unmount(); client.dispose();
});

it("unmount_drops_pending_retry_and_cleans_signal_without_success_toast", async () => {
  const rpc = testClient(), pending = deferred<unknown>();
  const read = rpc.call.getMockImplementation()!;
  rpc.call.mockImplementation((method, params) => method === "scan.retryBatch" ? pending.promise : read(method, params));
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  const { result, unmount } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.open(detailFixture.run.runId));
  await waitFor(() => expect(result.current.detail).not.toBeNull());
  let operation!: Promise<void>;
  act(() => { operation = result.current.retry(detailFixture.batches[2]!.batchId); });
  const options = (rpc.call.mock.calls as unknown[][]).find(([m]) => m === "scan.retryBatch")?.[2] as CallOptions;
  unmount(); expect(options.signal?.aborted).toBe(true);
  await act(async () => { pending.resolve({ ...detailFixture.batches[2], status: "succeeded" }); await operation; });
  expect(toast).not.toHaveBeenCalled();
  window.removeEventListener("sentinel:toast", toast);
});

it("budget_updates_use_notification_values_and_ignore_other_market", async () => {
  const rpc = testClient(), { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => {
    rpc.emit("budget.updated", { usedTokens: 2000000, limitTokens: 2000000, resetAt: historyFixture.budget.resetAt });
    rpc.emit("scan.progress", { ...progress, market: "hk" });
  });
  expect(result.current.budget?.usedTokens).toBe(2000000);
  expect(result.current.progress).toEqual({});
});

it("finished_event_overtakes_old_detail_snapshot", async () => {
  const rpc = testClient(), snapshot = deferred<unknown>();
  rpc.call.mockImplementation(async method => method === "scan.history" ? { ...historyFixture, items: [running] } : snapshot.promise);
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.open(running.runId));
  rpc.call.mockImplementation(async method => method === "scan.history" ? historyFixture : { run: historyFixture.items[0], batches: [] });
  await act(async () => { rpc.emit("scan.finished", historyFixture.items[0]!); });
  await act(async () => { snapshot.resolve({ run: running, batches: [] }); });
  expect(result.current.detail?.run.status).toBe("succeeded");
});

it("cancel_timeout_refreshes_real_interrupted_state", async () => {
  const rpc = testClient();
  let cancelled = false;
  const interrupted: ScanRun = { ...running, status: "interrupted" };
  rpc.call.mockImplementation(async method => {
    if (method === "scan.cancel") { cancelled = true; throw new RpcError("TIMEOUT", "synthetic cancel timeout", true); }
    if (method === "scan.status") return interrupted;
    return { ...historyFixture, items: [cancelled ? interrupted : running] };
  });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { await result.current.control.cancel(running.runId); });
  expect(result.current.runs[0]?.status).toBe("interrupted");
  expect(result.current.actionError?.code).toBe("TIMEOUT");
});

it("new_run_progress_from_shared_client_locks_start_and_queries_wire_status_once", async () => {
  const rpc = testClient(), snapshot = deferred<unknown>();
  rpc.call.mockImplementation(async method => method === "scan.history" ? historyFixture : snapshot.promise);
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  const event = { ...progress, runId: "synthetic-shared-run" };
  act(() => {
    rpc.emit("scan.progress", event);
    rpc.emit("scan.progress", { ...event, done: 2 });
  });
  expect(result.current.control.activeRunId).toBe(event.runId);
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.status").length).toBe(1);
  await act(async () => { await result.current.control.start(); });
  expect(rpc.call.mock.calls.some(([m]) => m === "scan.start")).toBe(false);
  await act(async () => { snapshot.resolve({ ...running, runId: event.runId }); });
  expect(result.current.runs[0]?.runId).toBe(event.runId);
  expect(result.current.runs[0]?.stats).toEqual(running.stats);
});

it("retry_timeout_stops_waiting_while_reconciliation_disables_duplicate_requests", async () => {
  const rpc = testClient(), refreshed = deferred<unknown>();
  const read = rpc.call.getMockImplementation()!;
  let retryStarted = false;
  rpc.call.mockImplementation(async (method, params) => {
    if (method === "scan.retryBatch") { retryStarted = true; throw new RpcError("TIMEOUT", "synthetic deadline", true); }
    if (method === "scan.detail" && retryStarted) return refreshed.promise;
    return read(method, params);
  });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.open(detailFixture.run.runId));
  await waitFor(() => expect(result.current.detail).not.toBeNull());
  const id = detailFixture.batches[2]!.batchId;
  let operation!: Promise<void>;
  act(() => { operation = result.current.retry(id); });
  await waitFor(() => expect(result.current.reconciling).toContain(id));
  expect(result.current.retrying).toEqual([]);
  expect(result.current.retryErrors[id]?.code).toBe("TIMEOUT");
  await act(async () => { await result.current.retry(id); });
  expect(rpc.call.mock.calls.filter(([m]) => m === "scan.retryBatch").length).toBe(1);
  await act(async () => { refreshed.resolve(detailFixture); await operation; });
  expect(result.current.reconciling).toEqual([]);
});

it("terminal_state_cannot_regress_but_partial_can_upgrade_to_succeeded", async () => {
  const rpc = testClient();
  rpc.call.mockResolvedValue({ ...historyFixture, items: [detailFixture.run] });
  const { result } = mounted(rpc);
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { rpc.emit("scan.finished", { ...detailFixture.run, status: "succeeded" }); });
  expect(result.current.runs[0]?.status).toBe("succeeded");
  await act(async () => { await result.current.refresh(); });
  expect(result.current.runs[0]?.status).toBe("succeeded");
});
