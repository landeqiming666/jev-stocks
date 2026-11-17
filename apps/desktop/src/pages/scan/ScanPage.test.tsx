import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "../../app/store";
import bootstrap from "../../app/__fixtures__/bootstrap.json";
import type { Bootstrap } from "../../rpc";
import { RpcError } from "../../rpc";
import ScanPage from "./index";
import { detailFixture, historyFixture, testClient } from "./test-support";

let rpc: ReturnType<typeof testClient>;
beforeEach(() => {
  rpc = testClient();
  useAppStore.setState({ client: rpc.client, bootstrap: { status: "ready", value: bootstrap as Bootstrap, error: null } });
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); });
function running() {
  const run = { ...historyFixture.items[0]!, status: "running" as const, finishedAt: null };
  rpc.call.mockImplementation(async method => method === "scan.history" ? { ...historyFixture, items: [run] } :
    method === "scan.status" ? run : { ok: true });
  return run;
}

describe("scan page required acceptance", () => {
  it("scan_history_renders_four_runs", async () => {
    render(<ScanPage />);
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(5));
    expect(screen.getAllByText("成功").length).toBe(2);
    expect(screen.getByText("部分成功")).toBeTruthy();
    expect(screen.getByText("已取消")).toBeTruthy();
  });
  it("scan_empty_shows_start_action", async () => {
    rpc.call.mockResolvedValue({ ...historyFixture, items: [] });
    render(<ScanPage />);
    await screen.findByText("还没有扫描记录");
    expect(screen.getAllByRole("button", { name: "立即扫描" }).length).toBe(1);
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("running_row_shows_done_total", async () => {
    const run = running(); render(<ScanPage />);
    await screen.findByText("进行中");
    act(() => rpc.emit("scan.progress", { runId: run.runId, market: "us", stage: "decide", done: 9, total: 17, message: "正在判定 ZZCL 的 6-K" }));
    await screen.findByText("9 / 17");
  });
  it("start_disabled_when_running", async () => {
    running(); render(<ScanPage />); await screen.findByText("进行中");
    const start = screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    expect(start.title).toContain("扫描正在进行");
  });
  it("cancel_sends_run_id", async () => {
    const run = running(); render(<ScanPage />); await screen.findByText("进行中");
    fireEvent.click(screen.getByRole("button", { name: "取消扫描" }));
    await waitFor(() => expect(rpc.call.mock.calls.some(([method]) => method === "scan.cancel")).toBe(true));
    const call = (rpc.call.mock.calls as unknown[][]).find(([method]) => method === "scan.cancel");
    expect(call?.[1]).toEqual({ runId: run.runId });
    expect(screen.getByText("进行中")).toBeTruthy();
  });
  it("detail_renders_failed_batch_reason", async () => {
    render(<ScanPage />); fireEvent.click(await screen.findByText("部分成功"));
    await screen.findByText(/Jev 返回 529（服务过载），已重试 3 次/);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
  it("retry_batch_calls_rpc_once", async () => {
    render(<ScanPage />); fireEvent.click(await screen.findByText("部分成功"));
    const retry = await screen.findByRole("button", { name: "重试" });
    fireEvent.click(retry); fireEvent.click(retry);
    await waitFor(() => expect(rpc.call.mock.calls.filter(([m]) => m === "scan.retryBatch").length).toBe(1));
    const call = (rpc.call.mock.calls as unknown[][]).find(([m]) => m === "scan.retryBatch");
    expect(call?.[1]).toEqual({ batchId: detailFixture.batches[2]!.batchId });
  });
  it("retry_failure_keeps_failed_status", async () => {
    rpc.call.mockImplementation(async method => {
      if (method === "scan.retryBatch") throw new RpcError("MODEL_ERROR", "Jev 529 retry rejected", true);
      return method === "scan.history" ? historyFixture : detailFixture;
    });
    render(<ScanPage />); fireEvent.click(await screen.findByText("部分成功"));
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    await screen.findByText(/Jev 529 retry rejected/);
    expect(screen.getByText("失败")).toBeTruthy();
    expect(screen.getByText(/已重试 3 次/)).toBeTruthy();
  });
});
