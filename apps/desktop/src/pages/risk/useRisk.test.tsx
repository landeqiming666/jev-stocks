import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { RpcError, type RiskResult } from "../../rpc";
import { useRisk } from "./useRisk";
import { clientFixture, deferred } from "./test-client";
import { ok } from "./__fixtures__/results";

afterEach(cleanup);
describe("risk request lifecycle", () => {
  it("risk_ignores_stale_response", async () => {
    const { client, call } = clientFixture();
    const early = deferred<RiskResult>(), late = deferred<RiskResult>();
    call.mockResolvedValueOnce(ok).mockReturnValueOnce(early.promise).mockReturnValueOnce(late.promise);
    const { result } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    act(() => result.current.setWindow("6M"));
    await waitFor(() => expect(call).toHaveBeenCalledTimes(2));
    const signal = call.mock.calls[1]![2].signal as AbortSignal;
    act(() => result.current.setWindow("1Y"));
    await waitFor(() => expect(call).toHaveBeenCalledTimes(3));
    expect(signal.aborted).toBe(true);
    await act(async () => late.resolve({ ...ok, window: { ...ok.window, observations: 200 } }));
    await act(async () => early.resolve({ ...ok, window: { ...ok.window, label: "6M", observations: 42 } }));
    expect(result.current.result?.window.observations).toBe(200);
  });
  it("old_error_cannot_overwrite_new_success", async () => {
    const { client, call } = clientFixture();
    const old = deferred<RiskResult>();
    call.mockReturnValueOnce(old.promise).mockResolvedValue(ok);
    const { result } = renderHook(() => useRisk(client));
    act(() => result.current.setWindow("6M"));
    await waitFor(() => expect(result.current.result).toBe(ok));
    await act(async () => old.reject(new RpcError("INTERNAL", "旧错误")));
    expect(result.current.error).toBeNull();
  });
  it("unmount_aborts_and_never_disposes_shared_client", async () => {
    const { client, call } = clientFixture();
    const pending = deferred<RiskResult>();
    call.mockReturnValue(pending.promise);
    const { unmount } = renderHook(() => useRisk(client));
    const signal = call.mock.calls[0]![2].signal as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve(ok));
    expect(client.dispose).not.toHaveBeenCalled();
  });
  it("strictmode_restarts_after_cleanup_and_ignores_first_setup", async () => {
    const { client, call } = clientFixture();
    const first = deferred<RiskResult>();
    call.mockReturnValueOnce(first.promise).mockResolvedValue(ok);
    const { result } = renderHook(() => useRisk(client), { reactStrictMode: true });
    await waitFor(() => expect(result.current.result).toBe(ok));
    expect(call.mock.calls[0]![2].signal.aborted).toBe(true);
    await act(async () => first.resolve({ ...ok, annualizedVol: 0.9 }));
    expect(result.current.result?.annualizedVol).toBe(0.187);
  });
  it("bootstrap_ready_and_replaced_client_control_requests", async () => {
    const first = clientFixture(), second = clientFixture();
    const pending = deferred<RiskResult>();
    first.call.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(({ client, ready }) => useRisk(client, ready), {
      initialProps: { client: first.client, ready: false },
    });
    expect(first.call).not.toHaveBeenCalled();
    rerender({ client: first.client, ready: true });
    expect(first.call).toHaveBeenCalledTimes(1);
    rerender({ client: second.client, ready: true });
    await waitFor(() => expect(result.current.result).toBe(ok));
    await act(async () => pending.resolve({ ...ok, annualizedVol: 0.99 }));
    expect(result.current.result).toBe(ok);
    expect(first.client.dispose).not.toHaveBeenCalled();
  });
  it("price_refresh_then_compute_is_serial_and_window_uses_latest", async () => {
    const { client, call } = clientFixture();
    const price = deferred<{ updated: number; failed: []; asOf: string }>();
    call.mockResolvedValueOnce(ok).mockReturnValueOnce(price.promise).mockResolvedValue(ok);
    const { result } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    let refresh!: Promise<void>;
    act(() => { refresh = result.current.refreshPrices(); });
    expect(call.mock.lastCall?.[0]).toBe("prices.refresh");
    act(() => result.current.setWindow("3Y"));
    expect(call).toHaveBeenCalledTimes(2);
    await act(async () => { price.resolve({ updated: 5, failed: [], asOf: "2026-10-30" }); await refresh; });
    await waitFor(() => expect(call.mock.lastCall?.[1]).toEqual({ scope: "holdings", window: "3Y", currency: "USD" }));
    expect(call).toHaveBeenCalledTimes(3);
  });
  it("price_failure_preserves_cache_and_recompute_can_retry", async () => {
    const { client, call } = clientFixture();
    const { result } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    call.mockRejectedValueOnce(new RpcError("RATE_LIMITED", "请求过于频繁"));
    await act(async () => { await result.current.refreshPrices(); });
    expect(result.current.result).toBe(ok);
    expect(result.current.error?.code).toBe("RATE_LIMITED");
    await act(async () => { await result.current.refresh(); });
    expect(result.current.error).toBeNull();
  });
  it("partial_price_failure_is_visible_without_claiming_updated_risk", async () => {
    const { client, call } = clientFixture();
    const { result } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    call.mockResolvedValueOnce({ updated: 4, failed: [{ instrumentId: "us:ZZAR", error: { code: "SOURCE_UNAVAILABLE", message: "缺行情" } }], asOf: "2026-10-30" });
    await act(async () => { await result.current.refreshPrices(); });
    expect(result.current.result).toBe(ok);
    expect(result.current.error?.message).toContain("us:ZZAR");
    expect(call).toHaveBeenCalledTimes(2);
  });
  it("duplicate_refresh_does_not_overlap_price_or_compute", async () => {
    const { client, call } = clientFixture();
    const price = deferred<{ updated: number; failed: []; asOf: string }>();
    call.mockResolvedValueOnce(ok).mockReturnValueOnce(price.promise).mockResolvedValue(ok);
    const { result } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    let a!: Promise<void>, b!: Promise<void>;
    act(() => { a = result.current.refreshPrices(); b = result.current.refreshPrices(); });
    expect(call).toHaveBeenCalledTimes(2);
    await act(async () => { price.resolve({ updated: 5, failed: [], asOf: "2026-10-30" }); await Promise.all([a, b]); });
    expect(call).toHaveBeenCalledTimes(3);
  });
  it("unmount_aborts_pending_prices_and_no_compute_follows", async () => {
    const { client, call } = clientFixture();
    const price = deferred<{ updated: number; failed: []; asOf: string }>();
    call.mockResolvedValueOnce(ok).mockReturnValueOnce(price.promise);
    const { result, unmount } = renderHook(() => useRisk(client));
    await waitFor(() => expect(result.current.result).toBe(ok));
    let task!: Promise<void>;
    act(() => { task = result.current.refreshPrices(); });
    const signal = call.mock.lastCall?.[2].signal as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { price.resolve({ updated: 5, failed: [], asOf: "2026-10-30" }); await task; });
    expect(call).toHaveBeenCalledTimes(2);
  });
});
