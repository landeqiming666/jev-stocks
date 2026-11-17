import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RiskPage from "./index";
import { useAppStore } from "../../app/store";
import bootstrapWire from "../../app/__fixtures__/bootstrap-unconfigured.json";
import type { Bootstrap } from "../../rpc";
import { RpcError } from "../../rpc";
import insufficient from "./__fixtures__/insufficient.json";
import { clientFixture } from "./test-client";
import { resultFor } from "./__fixtures__/results";

let rpc: ReturnType<typeof clientFixture>;
beforeEach(() => {
  rpc = clientFixture();
  useAppStore.setState({ client: rpc.client, bootstrap: {
    status: "ready", value: bootstrapWire as Bootstrap, error: null,
  } });
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); });
describe("risk page", () => {
  it("risk_renders_four_metrics", async () => {
    const { container } = render(<RiskPage />);
    for (const value of ["18.7%", "21.4%", "4.67", "69.3%"]) expect(await screen.findByText(value)).toBeTruthy();
    expect(container.querySelectorAll(".c-metric").length).toBe(4);
    expect(screen.getByText(/按当前权重回看/)).toBeTruthy();
    expect(screen.getByText(/252/)).toBeTruthy();
  });
  it("risk_table_toggle_replaces_svg", async () => {
    render(<RiskPage />);
    await screen.findByRole("img", { name: /相关系数/ });
    fireEvent.click(screen.getByRole("button", { name: "表格视图" }));
    expect(screen.queryByRole("img", { name: /相关系数/ })).toBeNull();
    expect(screen.getByRole("table", { name: /相关系数/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "表格视图" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("46.0%")).toBeTruthy();
  });
  it("risk_insufficient_hides_metrics", async () => {
    rpc.call.mockRejectedValue(RpcError.fromWire(insufficient));
    const { container } = render(<RiskPage />);
    expect(await screen.findByText(/至少需要 60 天/)).toBeTruthy();
    expect(container.querySelectorAll(".c-metric").length).toBe(0);
    expect(screen.queryByText("18.7%")).toBeNull();
  });
  it("risk_single_shows_two_asset_message", async () => {
    rpc.call.mockResolvedValue(resultFor("single"));
    render(<RiskPage />);
    expect(await screen.findByText(/至少需要 2 只持仓/)).toBeTruthy();
    expect(screen.getByText(/主成分分析至少需要 2 只标的/)).toBeTruthy();
    expect(screen.getByText("18.7%")).toBeTruthy();
  });
  it("risk_window_change_requests_new_window", async () => {
    render(<RiskPage />);
    await screen.findByText("18.7%");
    fireEvent.click(screen.getByRole("radio", { name: "6M" }));
    await waitFor(() => expect(rpc.call).toHaveBeenLastCalledWith("risk.compute", {
      scope: "holdings", currency: "USD", window: "6M",
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })));
  });
  it("keyboard_window_currency_v1_and_no_paper_scope", async () => {
    render(<RiskPage />);
    await screen.findByText("18.7%");
    fireEvent.keyDown(screen.getByRole("radio", { name: "1Y" }), { key: "ArrowRight" });
    await waitFor(() => expect(rpc.call.mock.lastCall?.[1].window).toBe("3Y"));
    const cny = screen.getByRole("radio", { name: "人民币" }) as HTMLButtonElement;
    expect(cny.disabled).toBe(true);
    expect(cny.title).toContain("v1");
    expect(screen.queryByRole("radio", { name: /模拟/ })).toBeNull();
  });
  it("warnings_actual_dates_exclusions_and_conditions_are_visible", async () => {
    const result = resultFor("unadjusted", "3Y");
    result.conditionNumberRaw = null;
    result.warnings.push("协方差矩阵接近奇异");
    rpc.call.mockResolvedValue(result);
    render(<RiskPage />);
    expect(await screen.findByText("价格未复权")).toBeTruthy();
    expect(screen.queryByText(/价格已复权/)).toBeNull();
    expect(screen.getByText(/ZZCL 最新行情/)).toBeTruthy();
    expect(screen.getByText(/数据不足三年/)).toBeTruthy();
    expect(screen.getByText(/协方差矩阵接近奇异/)).toBeTruthy();
    expect(screen.getByText(/实际窗口 3Y/)).toBeTruthy();
    expect(screen.getByText(/2025-10-30 至 2026-10-30/)).toBeTruthy();
    expect(screen.getByText(/行情截止：2026-10-30/)).toBeTruthy();
    expect(screen.getByText(/未计入：ZZMD/)).toBeTruthy();
  });
  it("unconfigured_key_budget_and_offline_do_not_hide_local_risk", async () => {
    useAppStore.setState({ bootstrap: { status: "ready", value: { ...bootstrapWire, offline: true } as Bootstrap, error: null } });
    render(<RiskPage />);
    expect(await screen.findByText("18.7%")).toBeTruthy();
    expect(screen.queryByText(/离线模式/)).toBeNull();
    expect(rpc.call).toHaveBeenCalledTimes(1);
  });
  it("production_hash_state_does_not_replace_rpc", async () => {
    window.location.hash = "#/risk?state=insufficient";
    render(<RiskPage />);
    expect(await screen.findByText("18.7%")).toBeTruthy();
    expect(rpc.call).toHaveBeenCalledTimes(1);
  });
  it("recompute_failure_keeps_cache_and_marks_not_updated", async () => {
    render(<RiskPage />);
    await screen.findByText("18.7%");
    rpc.call.mockRejectedValue(new RpcError("SOURCE_UNAVAILABLE", "行情源暂时无法访问"));
    fireEvent.click(screen.getByRole("button", { name: "重新计算" }));
    expect(await screen.findByText(/数据未更新/)).toBeTruthy();
    expect(screen.getByText("18.7%")).toBeTruthy();
  });
  it("zero_variance_keeps_effective_holdings_and_null_cells", async () => {
    rpc.call.mockResolvedValue(resultFor("zero"));
    const { container } = render(<RiskPage />);
    await screen.findByText("4.67");
    expect(container.querySelectorAll(".c-heatmap__cell.is-na").length).toBe(25);
    expect(screen.getAllByText("0.0%").length).toBe(2);
  });
  it("insufficient_preserves_backend_limiting_asset_explanation", async () => {
    rpc.call.mockRejectedValue(new RpcError("DATA_INSUFFICIENT", "样本不足：共同交易日 42 天，至少需要 60 天。ZZCL 的有效一日收益最少，请刷新该标的行情。", false,
      { observations: 42, required: 60 }));
    render(<RiskPage />);
    expect(await screen.findByText(/ZZCL 的有效一日收益最少/)).toBeTruthy();
  });
  it("no_holdings_is_not_presented_as_zero_risk", async () => {
    rpc.call.mockRejectedValue(new RpcError("DATA_INSUFFICIENT", "没有可计算的持仓", false,
      { reason: "NO_HOLDINGS", observations: 0, required: 60 }));
    const { container } = render(<RiskPage />);
    expect(await screen.findByText("没有可计算的持仓")).toBeTruthy();
    expect(container.querySelectorAll(".c-metric").length).toBe(0);
  });
  it("insufficient_recompute_preserves_labelled_previous_cache", async () => {
    render(<RiskPage />);
    await screen.findByText("18.7%");
    rpc.call.mockRejectedValue(RpcError.fromWire(insufficient));
    fireEvent.click(screen.getByRole("radio", { name: "6M" }));
    expect(await screen.findByText(/数据未更新；/)).toBeTruthy();
    expect(screen.getByText(/实际窗口 1Y/)).toBeTruthy();
    expect(screen.getByText("18.7%")).toBeTruthy();
  });
});
