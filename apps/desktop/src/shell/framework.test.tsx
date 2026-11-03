import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RpcError, type Bootstrap, type DataStatus } from "../rpc";
import ready from "../app/__fixtures__/bootstrap.json";
import unconfigured from "../app/__fixtures__/bootstrap-unconfigured.json";
import { useAppStore } from "../app/store";
import { AppShell } from "./AppShell";
import { PageFrame } from "./PageFrame";
import { safeErrorDetails, StartupFailure } from "./StartupFailure";

beforeEach(() => { useAppStore.getState().reset(); window.history.replaceState(null, "", "#/today"); });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });
function load(value: Bootstrap = ready as Bootstrap) { useAppStore.setState({ bootstrap: { status: "ready", value, error: null } }); }
it("bootstrap_cannot_fabricate_market_usage_or_successful_scan", () => {
  load(); render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("市场状态未就绪")).toBeTruthy();
  expect(screen.getByText("未就绪")).toBeTruthy();
  expect(screen.getAllByText("未知")).toHaveLength(2);
  expect(useAppStore.getState().dataStatus).toBeNull();
  expect(useAppStore.getState().budget).toBeNull();
  expect(screen.queryByText(/开盘中|已收盘|0 \/ .*tokens/)).toBeNull();
});
it("status_bar_renders_real_core_microsecond_timestamps_without_missing_values", () => {
  load();
  const timestamp = "2026-11-02T00:35:00.123456Z";
  useAppStore.setState({ dataAsOf: timestamp, lastSuccessfulScanAt: timestamp });
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  const status = document.querySelector(".l-status")!;
  expect(status.textContent).not.toContain("—");
  expect(status.textContent).not.toContain("未知");
  expect(screen.getByText("市场状态未就绪")).toBeTruthy();
  expect(useAppStore.getState().budget).toBeNull();
});
it("preview_marks_fixture_engine_as_example_data", () => {
  vi.stubEnv("VITE_RPC", "mock"); load();
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("界面预览 · 示例数据")).toBeTruthy();
  expect(screen.getByTitle("示例引擎")).toBeTruthy();
});
it("page_can_update_data_status_market_and_explicit_scan_and_budget", () => {
  load();
  const data: DataStatus = { market: "us", marketState: "closed", nextOpenAt: "2026-11-02T14:30:00Z",
    source: { name: "SEC", state: "ok", lastSuccessAt: ready.now, message: null },
    engine: { active: "jev_direct", modelId: "jev-1.14.0", state: "ok" },
    budget: { usedTokens: 7, limitTokens: 100, resetAt: ready.now }, offline: false };
  useAppStore.getState().setDataStatus(data, ready.now);
  useAppStore.getState().setLastSuccessfulScanAt(ready.now);
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText(/美股 已收盘 · 下次开盘/)).toBeTruthy();
  expect(document.documentElement.dataset.market).toBe("us");
  expect(screen.getByText("7 / 100 tokens")).toBeTruthy();
  expect(screen.queryByText(/已降级/)).toBeNull();
  act(() => useAppStore.getState().setDataStatus({ ...data, offline: true }));
  expect(screen.getByText("离线")).toBeTruthy();
  expect(screen.getByText("当前离线，显示的是上次的结果。")).toBeTruthy();
  act(() => useAppStore.getState().setDataStatus(null));
  expect(document.documentElement.dataset.market).toBeUndefined();
});
it("unconfigured_banner_hides_in_settings_and_engine_does_not_claim_connection", () => {
  load(unconfigured as Bootstrap); render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("引擎未配置")).toBeTruthy();
  fireEvent.click(screen.getByText("去设置"));
  expect(screen.queryByText("尚未配置 Jev 密钥和 SEC 联系邮箱，扫描无法开始。")).toBeNull();
});
it.each(["auto", "jevdb"] as const)("startup_%s_fallback_is_visible_without_data_status_or_engine_notification", requested => {
  load({ ...ready as Bootstrap, engine: { ...ready.engine, requested, active: "jev_direct", jevdbAvailable: false } });
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("Jev 直连 · jev-1.14.0 · 已降级")).toBeTruthy();
  expect(useAppStore.getState().dataStatus).toBeNull();
  expect(useAppStore.getState().ui.engineNotice).toBe(false);
  expect(screen.getByText("市场状态未就绪")).toBeTruthy();
});
it("explicit_direct_engine_does_not_claim_startup_fallback", () => {
  load({ ...ready as Bootstrap, engine: { ...ready.engine, requested: "jev_direct", active: "jev_direct", jevdbAvailable: false } });
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("Jev 直连 · jev-1.14.0")).toBeTruthy();
  expect(screen.queryByText(/已降级/)).toBeNull();
});
it("available_jevdb_does_not_claim_unavailable_startup_fallback", () => {
  load({ ...ready as Bootstrap, engine: { ...ready.engine, requested: "auto", active: "jev_direct", jevdbAvailable: true } });
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText("Jev 直连 · jev-1.14.0")).toBeTruthy();
  expect(screen.queryByText(/已降级/)).toBeNull();
});
it.each([
  [{ jevKey: false, secEmail: true }, "尚未配置 Jev 密钥，扫描无法开始。"],
  [{ jevKey: true, secEmail: false }, "尚未配置 SEC 联系邮箱，扫描无法开始。"],
  [{ jevKey: false, secEmail: false }, "尚未配置 Jev 密钥和 SEC 联系邮箱，扫描无法开始。"],
] as const)("configuration_banner_names_only_missing_fields: %j", (configured, message) => {
  load({ ...ready as Bootstrap, configured });
  render(<AppShell><PageFrame>Page</PageFrame></AppShell>);
  expect(screen.getByText(message)).toBeTruthy();
  fireEvent.click(screen.getByText("去设置"));
  expect(screen.queryByText(message)).toBeNull();
});
it("page_frame_only_renders_labeled_aside_when_open", () => {
  const view = render(<PageFrame aside={<p>Evidence</p>} asideLabel="Evidence panel">Page</PageFrame>);
  expect(screen.queryByRole("complementary")).toBeNull();
  view.rerender(<PageFrame aside={<p>Evidence</p>} asideLabel="Evidence panel" asideOpen>Page</PageFrame>);
  expect(screen.getByRole("complementary", { name: "Evidence panel" }).className).toBe("l-drawer");
  expect(document.querySelector(".l-content.has-drawer .l-scrim")).toBeTruthy();
});
it("safe_details_and_visible_failure_never_include_raw_message_stack_or_data", async () => {
  const secret = "Bearer private-key-do-not-expose";
  const error = new RpcError("INTERNAL", secret, false, { detail: secret, requestId: secret });
  error.stack = secret;
  expect(safeErrorDetails(error)).not.toContain(secret);
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<StartupFailure error={error} onRetry={vi.fn()} />);
  expect(document.body.textContent).not.toContain(secret);
  expect(screen.getByRole("heading", { level: 1 })).toBe(document.activeElement);
  fireEvent.click(screen.getByText("复制错误详情"));
  await screen.findByText("错误详情已复制。");
  expect(writeText.mock.calls[0]?.[0]).toBe(safeErrorDetails(error));
  writeText.mockRejectedValue(new Error(secret));
  fireEvent.click(screen.getByText("复制错误详情"));
  await waitFor(() => expect(screen.getByText("无法复制错误详情，请重试。")).toBeTruthy());
});
