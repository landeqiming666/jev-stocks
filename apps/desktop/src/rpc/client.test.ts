import { afterEach, expect, test, vi } from "vitest";
import { deferred, FakeTransport, waitFor } from "./test-fixtures";
import { RpcError, RPC_MESSAGES } from "./errors";

afterEach(() => { vi.useRealTimers(); });

async function setup() {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport();
  const client = createRpcClient({ transport });
  await waitFor();
  transport.ready();
  return { client, transport };
}

test("call_resolves_result_and_uses_expected_id_shape", async () => {
  const { client, transport } = await setup();
  const result = client.call("app.ping", {});
  await waitFor();
  expect(transport.lines[0]?.id).toMatch(/^r-\d+-[0-9a-f]{8}$/);
  transport.respond({ ok: true, uptimeMs: 10 });
  await expect(result).resolves.toEqual({ ok: true, uptimeMs: 10 });
  client.dispose();
});

test("wire_error_becomes_rpc_error", async () => {
  const { client, transport } = await setup();
  const result = client.call("app.ping", {});
  const error = { code: "INVALID_ARGUMENT", message: "逻辑内容不能为空", data: { retryable: false } };
  const assertion = expect(result).rejects.toMatchObject({ ...error, retryable: false });
  await waitFor();
  transport.message({ jsonrpc: "2.0", id: transport.lines[0]?.id, error });
  await assertion;
  client.dispose();
});

test("timeout_sends_cancel_and_rejects_timeout", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup();
  const result = client.call("app.ping", {}, { timeoutMs: 10 });
  const assertion = expect(result).rejects.toMatchObject({ code: "TIMEOUT" });
  await vi.advanceTimersByTimeAsync(10);
  await assertion;
  expect(transport.lines).toHaveLength(2);
  expect(transport.lines[1]).toEqual({ jsonrpc: "2.0", method: "$/cancel", params: { id: transport.lines[0]?.id } });
  transport.respond({ ok: true, uptimeMs: 1 });
  await vi.advanceTimersByTimeAsync(100);
  expect(transport.lines).toHaveLength(2);
  client.dispose();
});

test("restart_rejects_all_pending_calls", async () => {
  const { client, transport } = await setup();
  const assertions = [client.call("app.ping", {}), client.call("settings.get", {})]
    .map(p => expect(p).rejects.toMatchObject({ code: "INTERNAL" }));
  await waitFor();
  transport.emit("core://status", { state: "restarting", attempt: 1 });
  await Promise.all(assertions);
  expect(client.status()).toBe("restarting");
  client.dispose();
});

test("subscribe_receives_scan_progress", async () => {
  const { client, transport } = await setup();
  const handler = vi.fn();
  const unsubscribe = client.subscribe("scan.progress", handler);
  const params = { runId: "run-1", done: 9, total: 17 };
  transport.message({ jsonrpc: "2.0", method: "scan.progress", params });
  expect(handler).toHaveBeenCalledWith(params);
  unsubscribe();
  client.dispose();
});

test("waits_for_both_listeners_before_sending", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport();
  const gate = deferred<() => void>();
  const original = transport.listen;
  transport.listen = vi.fn(async (name, handler) => {
    const off = await original(name, handler);
    if (name === "core://message") await gate.promise;
    return off;
  });
  transport.invoke.mockResolvedValueOnce({ state: "ready", attempt: 0 });
  const client = createRpcClient({ transport });
  const result = client.call("app.ping", {});
  await waitFor();
  expect(transport.invoke).not.toHaveBeenCalled();
  gate.resolve(() => {});
  await waitFor();
  expect(client.status()).toBe("ready");
  expect(transport.lines).toHaveLength(1);
  transport.respond({ ok: true, uptimeMs: 1 });
  await expect(result).resolves.toEqual({ ok: true, uptimeMs: 1 });
  client.dispose();
});

test("snapshot_recovers_ready_emitted_before_listen", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport();
  transport.invoke.mockResolvedValue({ state: "ready", attempt: 0 });
  const client = createRpcClient({ transport });
  await client.whenReady();
  expect(client.status()).toBe("ready");
  expect(transport.invoke).toHaveBeenCalledExactlyOnceWith("core_status");
  expect(transport.listen).toHaveBeenCalledTimes(2);
  client.dispose();
});

test.each(["ready", "restarting", "failed"] as const)("snapshot_cannot_overwrite_new_%s_event", async state => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), snapshot = deferred<unknown>();
  transport.invoke.mockReturnValue(snapshot.promise);
  const client = createRpcClient({ transport });
  await waitFor();
  transport.emit("core://status", { state, attempt: 1 });
  snapshot.resolve({ state: state === "ready" ? "starting" : "ready", attempt: 0 });
  await waitFor();
  expect(client.status()).toBe(state);
  client.dispose();
});

test("when_ready_waits_through_starting_and_restarting", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), done = vi.fn();
  const client = createRpcClient({ transport });
  const ready = client.whenReady().then(done);
  await waitFor();
  expect(done).not.toHaveBeenCalled();
  transport.emit("core://status", { state: "restarting", attempt: 1 });
  await waitFor();
  expect(done).not.toHaveBeenCalled();
  transport.ready(); await ready;
  expect(done).toHaveBeenCalledOnce();
  client.dispose();
});

test("not_ready_rejects_without_rpc_send", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), client = createRpcClient({ transport });
  await expect(client.call("app.ping", {})).rejects.toMatchObject({ code: "INTERNAL", retryable: true, message: RPC_MESSAGES.notReady });
  expect(transport.lines).toHaveLength(0);
  client.dispose();
});

test("already_aborted_signal_never_sends_request", async () => {
  const { client, transport } = await setup();
  const controller = new AbortController(); controller.abort();
  await expect(client.call("app.ping", {}, { signal: controller.signal })).rejects.toMatchObject({ code: "CANCELLED" });
  expect(transport.lines).toHaveLength(0);
  client.dispose();
});

test.each(["abort", "timeout"] as const)("%s_during_listener_setup_clears_call_without_sending", async kind => {
  vi.useFakeTimers();
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), gate = deferred<() => void>();
  transport.listen.mockReturnValue(gate.promise);
  const client = createRpcClient({ transport }), controller = new AbortController();
  const result = client.call("app.ping", {}, { signal: controller.signal, timeoutMs: 10 });
  const assertion = expect(result).rejects.toMatchObject({ code: kind === "abort" ? "CANCELLED" : "TIMEOUT" });
  if (kind === "abort") controller.abort(); else await vi.advanceTimersByTimeAsync(10);
  await assertion;
  gate.resolve(() => {}); await waitFor();
  expect(transport.lines).toHaveLength(0);
  expect(vi.getTimerCount()).toBe(0);
  client.dispose();
});

test("abort_after_send_cancels_once_and_removes_listener", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup(), controller = new AbortController();
  const remove = vi.spyOn(controller.signal, "removeEventListener");
  const result = client.call("app.ping", {}, { signal: controller.signal });
  const assertion = expect(result).rejects.toMatchObject({ code: "CANCELLED" });
  await waitFor(); controller.abort(); await assertion;
  expect(transport.lines[1]?.method).toBe("$/cancel");
  expect(remove).toHaveBeenCalledOnce();
  transport.respond({ ok: true, uptimeMs: 1 });
  await vi.advanceTimersByTimeAsync(60_000);
  expect(transport.lines).toHaveLength(2);
  client.dispose();
});

test("successful_call_removes_abort_and_timeout_resources", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup(), controller = new AbortController();
  const remove = vi.spyOn(controller.signal, "removeEventListener");
  const result = client.call("app.ping", {}, { signal: controller.signal });
  await waitFor(); transport.respond({ ok: true, uptimeMs: 1 }); await result;
  controller.abort(); await vi.advanceTimersByTimeAsync(60_000);
  expect(remove).toHaveBeenCalledOnce(); expect(transport.lines).toHaveLength(1);
  expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test("send_failure_is_safe_rpc_error_and_cleans_pending", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup();
  transport.invoke.mockRejectedValue(new Error("sensitive transport detail"));
  await expect(client.call("app.ping", {})).rejects.toMatchObject({ code: "INTERNAL", message: RPC_MESSAGES.disconnected });
  expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test("listen_failure_disposes_successful_and_late_listeners", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), gate = deferred<() => void>(), off = vi.fn();
  transport.listen.mockImplementation(name => name === "core://status" ? Promise.reject(new Error("failed")) : gate.promise);
  const client = createRpcClient({ transport });
  await expect(client.whenReady()).rejects.toMatchObject({ code: "INTERNAL" });
  gate.resolve(off); await waitFor();
  expect(off).toHaveBeenCalledOnce(); expect(client.status()).toBe("failed");
});

test("dispose_during_setup_unlistens_late_resolutions", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), gates = [deferred<() => void>(), deferred<() => void>()], off = vi.fn();
  transport.listen.mockImplementationOnce(() => gates[0]!.promise).mockImplementationOnce(() => gates[1]!.promise);
  const client = createRpcClient({ transport }); client.dispose();
  gates.forEach(gate => gate.resolve(off)); await waitFor();
  expect(off).toHaveBeenCalledTimes(2); expect(transport.invoke).not.toHaveBeenCalled();
});

test("multiple_subscriptions_independently_unsubscribe_and_isolate_exceptions", async () => {
  const { client, transport } = await setup(), handler = vi.fn(), bad = vi.fn(() => { throw new Error("handler"); });
  const offBad = client.subscribe("scan.progress", bad);
  const off = client.subscribe("scan.progress", handler);
  client.subscribe("scan.progress", handler);
  const notification = { jsonrpc: "2.0", method: "scan.progress", params: { done: 9 } };
  transport.message(notification); expect(handler).toHaveBeenCalledTimes(2);
  off(); off(); offBad(); transport.message(notification);
  expect(handler).toHaveBeenCalledTimes(3);
  client.dispose(); transport.message(notification);
  expect(handler).toHaveBeenCalledTimes(3); expect(transport.unlisten).toHaveBeenCalledTimes(2);
});

test("bad_messages_unknown_ids_and_notifications_are_ignored_and_logs_are_bounded", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), warn = vi.fn(), client = createRpcClient({ transport, warn });
  await waitFor(); transport.ready();
  const result = client.call("app.ping", {}); await waitFor();
  for (let i = 0; i < 2; i++) {
    for (const payload of ["{", "null", "[]", "1", { result: {} }]) transport.emit("core://message", payload);
    transport.message({ jsonrpc: "1.0", id: transport.lines[0]?.id, result: {} });
    transport.message({ jsonrpc: "2.0", id: transport.lines[0]?.id, result: {}, error: {} });
    transport.message({ jsonrpc: "2.0", id: "unknown-" + i, result: {} });
    transport.message({ jsonrpc: "2.0", method: "unknown-" + i, params: {} });
  }
  expect(warn).toHaveBeenCalledTimes(4);
  transport.respond({ ok: true, uptimeMs: 1 }); await result; client.dispose();
});

test("unknown_wire_error_cannot_escape_errorcode_or_leak_message", async () => {
  const { client, transport } = await setup();
  const result = client.call("app.ping", {}), assertion = expect(result).rejects.toMatchObject({
    code: "INTERNAL", message: RPC_MESSAGES.internal, retryable: false, data: { retryable: false },
  });
  await waitFor(); transport.message({ jsonrpc: "2.0", id: transport.lines[0]?.id,
    error: { code: "FUTURE", message: "secret", data: { retryable: true, token: "secret" } } });
  await assertion; client.dispose();
});

test.each([null, 1, [], { code: "INTERNAL", message: "", data: null }])("malformed_wire_error_has_safe_fallback_%j", value => {
  const error = RpcError.fromWire(value);
  expect(error).toBeInstanceOf(RpcError); expect(error.code).toBe("INTERNAL");
  expect(error.message).toBe(RPC_MESSAGES.internal);
});

test("retry_preserves_frozen_params_and_idempotency_key", async () => {
  const { client, transport } = await setup();
  const params = Object.freeze({ accountId: "account", instrumentId: "us:ZZAR", side: "buy" as const,
    quantity: 100, orderType: "market_open" as const, idempotencyKey: "caller-owned-key" });
  for (let i = 0; i < 2; i++) {
    const result = client.call("paper.order.place", params);
    await waitFor(); expect(transport.lines[i]?.params).toEqual(params);
    transport.respond({}, i); await result;
  }
  expect(transport.lines[0]?.id).not.toEqual(transport.lines[1]?.id);
  expect(params.idempotencyKey).toBe("caller-owned-key"); client.dispose();
});

test.each(["app.ping", "scan.start", "settings.testConnection"] as const)("default_timeout_for_%s", async method => {
  vi.useFakeTimers();
  const { client, transport } = await setup();
  const result = client.call(method, method === "scan.start" ? { market: "us" } : {});
  const assertion = expect(result).rejects.toMatchObject({ code: "TIMEOUT" });
  const ms = method === "settings.testConnection" ? 20_000 : 30_000;
  await vi.advanceTimersByTimeAsync(ms - 1); expect(transport.lines).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1); await assertion;
  expect(transport.lines).toHaveLength(2); client.dispose();
});

test.each(["abort", "timeout", "failed", "dispose"] as const)("when_ready_%s_cleans_waiter", async kind => {
  vi.useFakeTimers();
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), client = createRpcClient({ transport }), controller = new AbortController();
  const promise = client.whenReady({ signal: controller.signal, timeoutMs: 10 });
  const assertion = expect(promise).rejects.toMatchObject({ code: kind === "abort" ? "CANCELLED" : kind === "timeout" ? "TIMEOUT" : "INTERNAL" });
  await waitFor();
  if (kind === "abort") controller.abort();
  if (kind === "timeout") await vi.advanceTimersByTimeAsync(10);
  if (kind === "failed") transport.emit("core://status", { state: "failed", attempt: 3 });
  if (kind === "dispose") client.dispose();
  await assertion; expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test("out_of_order_responses_match_pending_ids", async () => {
  const { client, transport } = await setup();
  const one = client.call("app.ping", {}), two = client.call("app.ping", {});
  await waitFor(); transport.respond({ ok: true, uptimeMs: 2 }, 1); transport.respond({ ok: true, uptimeMs: 1 }, 0);
  await expect(one).resolves.toMatchObject({ uptimeMs: 1 }); await expect(two).resolves.toMatchObject({ uptimeMs: 2 });
  client.dispose();
});

test("timeout_wins_over_synchronous_cancel_response", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup();
  const invoke = transport.invoke;
  transport.invoke = vi.fn(async (command, args) => {
    if (args && JSON.parse(args.line).method === "$/cancel") {
      transport.message({ jsonrpc: "2.0", id: transport.lines[0]?.id, error: { code: "CANCELLED", message: RPC_MESSAGES.cancelled, data: { retryable: false } } });
    }
    return invoke(command, args);
  });
  const result = client.call("app.ping", {}, { timeoutMs: 10 }), assertion = expect(result).rejects.toMatchObject({ code: "TIMEOUT" });
  await vi.advanceTimersByTimeAsync(10); await assertion;
  expect(transport.lines).toHaveLength(2); client.dispose();
});

test("synchronous_send_throw_is_handled", async () => {
  vi.useFakeTimers();
  const { client, transport } = await setup();
  transport.invoke.mockImplementation(() => { throw new Error("private failure"); });
  await expect(client.call("app.ping", {})).rejects.toMatchObject({ code: "INTERNAL" });
  expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test("cleanup_failure_still_releases_other_listeners", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), off = vi.fn(), warn = vi.fn();
  transport.listen.mockResolvedValueOnce(() => { throw new Error("unlisten failed"); }).mockResolvedValueOnce(off);
  const client = createRpcClient({ transport, warn }); await waitFor();
  client.dispose(); client.dispose();
  expect(off).toHaveBeenCalledOnce(); expect(warn).toHaveBeenCalledExactlyOnceWith("rpc: listener cleanup failed");
});

test("invalid_status_does_not_invalidate_snapshot", async () => {
  const { createRpcClient } = await import("./client");
  const transport = new FakeTransport(), gate = deferred<unknown>(), warn = vi.fn();
  transport.invoke.mockReturnValue(gate.promise);
  const client = createRpcClient({ transport, warn }); await waitFor();
  transport.emit("core://status", { state: "failed", attempt: "bad" });
  transport.emit("core://status", { state: { toString: "bad" }, attempt: 0 });
  gate.resolve({ state: "ready", attempt: 0 }); await client.whenReady();
  expect(client.status()).toBe("ready"); client.dispose();
});

test("when_ready_already_aborted_rejects_without_waiter", async () => {
  vi.useFakeTimers();
  const { client } = await setup(), controller = new AbortController(); controller.abort();
  await expect(client.whenReady({ signal: controller.signal })).rejects.toMatchObject({ code: "CANCELLED" });
  expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test.each([-1, NaN, Infinity])("invalid_timeout_%s_rejects_without_sending", async timeoutMs => {
  const { client, transport } = await setup();
  await expect(client.call("app.ping", {}, { timeoutMs })).rejects.toMatchObject({ code: "INVALID_ARGUMENT" });
  await expect(client.whenReady({ timeoutMs })).rejects.toMatchObject({ code: "INVALID_ARGUMENT" });
  expect(transport.lines).toHaveLength(0); client.dispose();
});

test("real_client_unknown_method_is_invalid_argument", async () => {
  const { client, transport } = await setup();
  await expect(client.call("unknown.method" as import("./generated/methods").MethodName, {})).rejects.toMatchObject({ code: "INVALID_ARGUMENT", data: { reason: "UNKNOWN_METHOD" } });
  expect(transport.lines).toHaveLength(0); client.dispose();
});
