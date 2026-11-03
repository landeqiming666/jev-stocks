import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { useAppStore } from "../../app/store";
import type { CoreStatusListener } from "../../lib/core-status";
import type { RpcClient } from "../../rpc/client";
import { createMockRpcClient } from "../../rpc/mock/client";
import { CoreStatusBanner } from "./CoreStatusBanner";

afterEach(() => { cleanup(); useAppStore.getState().reset(); vi.useRealTimers(); });
const tick = async () => { await act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); }); };
test("restarting_failed_and_recovered_timer_are_visible_using_store_client", async () => {
  vi.useFakeTimers();
  let emit: (payload: unknown) => void = () => {};
  const release = vi.fn();
  const listener: CoreStatusListener = async callback => { emit = callback; return release; };
  useAppStore.setState({ client: { status: () => "restarting" } as RpcClient });
  const view = render(<StrictMode><CoreStatusBanner listener={listener} /></StrictMode>);
  await tick();
  expect(screen.getByText("核心进程正在重启…")).toBeTruthy();
  act(() => emit({ state: "failed", attempt: 3 }));
  expect(screen.getByRole("alert").textContent).toContain("未能启动");
  act(() => emit({ state: "ready", attempt: 0 }));
  expect(screen.getByText("核心进程已恢复。")).toBeTruthy();
  act(() => vi.advanceTimersByTime(2999));
  act(() => emit({ state: "ready", attempt: 0 }));
  act(() => vi.advanceTimersByTime(1));
  expect(screen.queryByText("核心进程已恢复。")).toBeNull();
  act(() => emit({ state: "restarting", attempt: 1 }));
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
  expect(release).toHaveBeenCalledTimes(2);
});

test("already_ready_snapshot_is_quiet_and_client_change_removes_old_listener", async () => {
  const callbacks: ((payload: unknown) => void)[] = [], release = vi.fn();
  const listener: CoreStatusListener = async callback => { callbacks.push(callback); return release; };
  useAppStore.setState({ client: { status: () => "ready" } as RpcClient });
  render(<CoreStatusBanner listener={listener} />); await tick();
  expect(screen.queryByRole("status")).toBeNull();
  act(() => useAppStore.setState({ client: { status: () => "failed" } as RpcClient })); await tick();
  expect(release).toHaveBeenCalledTimes(1);
  act(() => callbacks[0]!({ state: "restarting", attempt: 1 }));
  expect(screen.getByRole("alert").textContent).toContain("未能启动");
  act(() => useAppStore.setState({ client: null }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(release).toHaveBeenCalledTimes(2);
});

test("failed_banner_delegates_retry_to_integration_without_creating_client", async () => {
  const onRetry = vi.fn();
  useAppStore.setState({ client: { status: () => "failed" } as RpcClient });
  render(<CoreStatusBanner listener={async () => () => {}} onRetry={onRetry} />); await tick();
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("real_c05_mock_client_status_is_consumed_without_any_business_rpc", async () => {
  const client = createMockRpcClient({ warn: () => {} });
  await client.whenReady();
  const call = vi.spyOn(client, "call"), dispose = vi.spyOn(client, "dispose");
  useAppStore.setState({ client });
  const view = render(<CoreStatusBanner listener={async () => () => {}} />); await tick();
  expect(screen.queryByRole("status")).toBeNull();
  expect(call).not.toHaveBeenCalled();
  view.unmount();
  expect(dispose).not.toHaveBeenCalled();
  client.dispose();
});
