import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAppStore } from "../../app/store";
import { AppShell } from "../../shell/AppShell";
import { FeedbackHost } from "../../components/feedback";
import bootstrap from "../../app/__fixtures__/bootstrap.json";
import { RpcError, type Bootstrap, type ScanRun } from "../../rpc";
import { cost, duration, engine, number, time } from "./format";
import { selectMockScenario } from "./mock-scenario";
import ScanPage from "./index";
import { detailFixture, historyFixture, testClient } from "./test-support";

let rpc: ReturnType<typeof testClient>;
beforeEach(() => {
  rpc = testClient();
  useAppStore.setState({ client: rpc.client, bootstrap: { status: "ready", value: bootstrap as Bootstrap, error: null } });
  window.history.replaceState(null, "", "#/scan");
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); vi.unstubAllEnvs(); });

it("all_seven_wire_statuses_render_without_missing_labels", async () => {
  const states: ScanRun["status"][] = ["queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted"];
  rpc.call.mockResolvedValue({ ...historyFixture, items: states.map((status, index) => ({ ...historyFixture.items[0], runId: `synthetic-status-${index}`, status })) });
  render(<ScanPage />);
  await waitFor(() => expect(screen.getAllByRole("row").length).toBe(8));
  for (const label of ["排队中", "进行中", "成功", "部分成功", "失败", "已取消", "已中断"]) expect(screen.getByText(label)).toBeTruthy();
});

it("unconfigured_keeps_cached_history_and_prevents_start_rpc", async () => {
  useAppStore.setState({ bootstrap: { status: "ready", value: { ...bootstrap as Bootstrap, configured: { jevKey: false, secEmail: false } }, error: null } });
  render(<ScanPage />);
  await screen.findByText("部分成功");
  const button = screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(button.title).toBe("请先完成设置");
  fireEvent.click(button);
  expect(rpc.call.mock.calls.some(([method]) => method === "scan.start")).toBe(false);
});

it("only_root_offline_banner_remains_and_history_is_readable", async () => {
  useAppStore.setState({ bootstrap: { status: "ready", value: { ...bootstrap as Bootstrap, offline: true }, error: null } });
  render(<AppShell globalFeedback><FeedbackHost><ScanPage /></FeedbackHost></AppShell>);
  await screen.findByText("部分成功");
  expect(screen.getAllByText("当前离线，显示的是上次的结果。").length).toBe(1);
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
});

it("history_error_preserves_code_message_and_reload_action", async () => {
  rpc.call.mockRejectedValueOnce(new RpcError("SOURCE_UNAVAILABLE", "synthetic history source failed", true));
  render(<ScanPage />);
  await screen.findByText(/SOURCE_UNAVAILABLE.*synthetic history source failed/);
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("部分成功");
});

it("loading_has_four_skeleton_rows_and_empty_has_no_table_head", async () => {
  let resolve!: (value: unknown) => void;
  rpc.call.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  render(<ScanPage />);
  expect(document.querySelectorAll(".c-skeleton").length).toBe(4);
  await act(async () => { resolve({ ...historyFixture, items: [] }); });
  expect(screen.getByText("还没有扫描记录")).toBeTruthy();
  expect(screen.queryByRole("table")).toBeNull();
});

it("keyboard_row_enter_space_esc_close_restores_origin_in_strictmode", async () => {
  render(<StrictMode><ScanPage /></StrictMode>);
  const label = await screen.findByText("部分成功");
  const row = label.closest("tr")!;
  row.focus(); fireEvent.keyDown(row, { key: "Enter" });
  await screen.findByRole("dialog");
  expect(document.activeElement?.id).toBe("scan-detail-title");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(row);
  fireEvent.keyDown(row, { key: " " });
  await screen.findByRole("dialog");
  fireEvent.click(screen.getByRole("button", { name: "关闭扫描明细" }));
  expect(document.activeElement).toBe(row);
});

it("detail_missing_and_empty_batches_keep_drawer_close_accessible", async () => {
  const read = rpc.call.getMockImplementation()!;
  rpc.call.mockImplementation(async (method, params) => {
    if (method === "scan.detail") throw new RpcError("NOT_FOUND", "synthetic missing run");
    return read(method, params);
  });
  render(<ScanPage />);
  fireEvent.click(await screen.findByText("部分成功"));
  await screen.findByText(/NOT_FOUND.*synthetic missing run/);
  expect(screen.getByRole("button", { name: "关闭扫描明细" })).toBeTruthy();
  rpc.call.mockImplementation((method, params) => method === "scan.detail" ? Promise.resolve({ ...detailFixture, batches: [] }) : read(method, params));
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("没有批次记录");
});

it("wire_cost_is_exact_unknown_fields_are_dashes_and_summary_is_not_recounted", async () => {
  expect(cost("0.000257")).toBe("$0.000257");
  expect([cost(null), number(null), duration(null), engine(null), time(null)]).toEqual(Array(5).fill("—"));
  render(<ScanPage />);
  const partial = await screen.findByText("部分成功"); fireEvent.click(partial);
  await screen.findByText("已返回批次 (4)");
  expect(screen.getByText("批次 5 · 成功 4 · 失败 1 · 待处理 0")).toBeTruthy();
  expect(document.querySelector(".p-scan__budget")?.textContent).toContain("估算 —");
});

it("production_hash_state_does_not_replace_data_or_select_mock_examples", async () => {
  vi.stubEnv("VITE_RPC", "production");
  const setExample = vi.fn();
  selectMockScenario(Object.assign(rpc.client, { setExample }), "budget");
  render(<ScanPage />);
  await screen.findByText("部分成功");
  act(() => {
    window.history.replaceState(null, "", "#/scan?state=budget");
    window.dispatchEvent(new Event("hashchange"));
  });
  expect(setExample).not.toHaveBeenCalled();
  expect(document.querySelector(".p-scan__budget.is-danger")).toBeNull();
  expect(rpc.call.mock.calls.filter(([method]) => method === "scan.history").length).toBe(1);
});

it("retry_success_uses_wire_batch_then_refreshes_server_stats_and_clears_error", async () => {
  let retried = false;
  const succeededBatch = { ...detailFixture.batches[2]!, status: "succeeded" as const, attempts: 4, error: null };
  const updated = { ...detailFixture, batches: detailFixture.batches.map(batch => batch.batchId === succeededBatch.batchId ? succeededBatch : batch) };
  rpc.call.mockImplementation(async method => {
    if (method === "scan.retryBatch") { retried = true; return succeededBatch; }
    if (method === "scan.detail") return retried ? updated : detailFixture;
    if (method === "scan.status") return detailFixture.run;
    return historyFixture;
  });
  render(<ScanPage />); fireEvent.click(await screen.findByText("部分成功"));
  fireEvent.click(await screen.findByRole("button", { name: "重试" }));
  await waitFor(() => expect(document.querySelector(`[data-batch-id="${succeededBatch.batchId}"]`)?.textContent).toContain("成功"));
  expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
});
