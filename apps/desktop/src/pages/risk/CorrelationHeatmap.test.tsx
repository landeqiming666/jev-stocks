import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { RiskTable } from "./RiskTable";
import { SvdPanel } from "./SvdPanel";
import { ok, resultFor } from "./__fixtures__/results";

afterEach(cleanup);
describe("risk charts", () => {
  it("risk_heatmap_has_aria_label", () => {
    render(<CorrelationHeatmap result={ok} table={false} />);
    expect(screen.getByRole("img", { name: /5 只标的/ })).toBeTruthy();
  });
  it("risk_heatmap_cell_title_has_pair", () => {
    const { container } = render(<CorrelationHeatmap result={ok} table={false} />);
    expect(container.querySelector('[data-row="0"][data-col="1"] title')?.textContent).toBe("ZZAR 与 ZZFD：ρ = 0.21");
  });
  it("risk_heatmap_uses_70_percent_max", () => {
    const result = structuredClone(ok);
    result.correlation.matrix[0]![1] = 1;
    const { container } = render(<CorrelationHeatmap result={result} table={false} />);
    expect(container.querySelector('[data-row="0"][data-col="1"] rect')?.getAttribute("style")).toContain("70%");
  });
  it("risk_null_cell_renders_dash_in_table", () => {
    render(<RiskTable result={resultFor("null")} />);
    expect(screen.getAllByText("—").length).toBe(9);
    expect(screen.getByText(/不可定义/)).toBeTruthy();
    expect(screen.getAllByRole("row").length).toBe(6);
  });
  it("preserves_null_diagonal_and_uses_hatching", () => {
    const { container } = render(<CorrelationHeatmap result={resultFor("null")} table={false} />);
    expect(container.querySelector('[data-row="2"][data-col="2"]')?.classList.contains("is-na")).toBe(true);
    expect(container.querySelectorAll(".c-heatmap__null").length).toBe(9);
    expect(container.querySelectorAll(".c-heatmap__cell").length).toBe(25);
  });
  it("cell_focus_and_arrows_show_rho_tooltip_and_escape_dismisses", () => {
    const { container } = render(<CorrelationHeatmap result={ok} table={false} />);
    const cell = container.querySelector<SVGGElement>('[data-row="0"][data-col="0"]')!;
    cell.focus();
    fireEvent.focus(cell);
    expect(screen.getByRole("tooltip").textContent).toContain("ρ = 1.00");
    fireEvent.keyDown(cell, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-col")).toBe("1");
    expect(screen.getByRole("tooltip").textContent).toContain("ρ = 0.21");
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
  it("table_preserves_raw_precision_as_accessible_cell_title", () => {
    const result = structuredClone(ok);
    result.correlation.matrix[0]![1] = 0.213456789012345;
    render(<RiskTable result={result} />);
    expect(screen.getByTitle("ZZAR 与 ZZFD：ρ = 0.213456789012345").textContent).toBe("0.21");
  });
  it("risk_svd_renders_five_bars", () => {
    const { container } = render(<SvdPanel result={ok} />);
    expect(container.querySelectorAll(".c-barlist__row").length).toBe(5);
    expect(screen.getByText("46.0%")).toBeTruthy();
    expect(container.querySelectorAll(".p-risk__loadings li").length).toBe(5);
  });
  it("svd_caps_five_and_sorts_loadings_by_absolute_value", () => {
    const result = structuredClone(ok);
    result.svd.explained.push(0);
    result.svd.loadings = [{ symbol: "ZZFD", value: -0.9 }, ...result.svd.loadings];
    const { container } = render(<SvdPanel result={result} />);
    expect(container.querySelectorAll(".c-barlist__row").length).toBe(5);
    expect(container.querySelector(".p-risk__loadings li")?.textContent).toBe("ZZFD-0.90");
  });
  it("zero_variance_is_empty_svd_but_weights_and_assets_survive", () => {
    const { container } = render(<SvdPanel result={resultFor("zero")} />);
    expect(container.querySelectorAll(".c-barlist__row").length).toBe(0);
    expect(screen.getByText(/资产无波动/)).toBeTruthy();
  });
  it("svd_accessible_image_names_include_numeric_proportions", () => {
    render(<SvdPanel result={ok} />);
    expect(screen.getByRole("img", { name: /46.0%/ })).toBeTruthy();
  });
  it("tooltip_uses_current_rho_after_same_window_refresh", () => {
    const { container, rerender } = render(<CorrelationHeatmap result={ok} table={false} />);
    fireEvent.focus(container.querySelector('[data-row="0"][data-col="1"]')!);
    const updated = structuredClone(ok);
    updated.correlation.matrix[0]![1] = 0.95;
    rerender(<CorrelationHeatmap result={updated} table={false} />);
    expect(screen.getByRole("tooltip").textContent).toContain("ρ = 0.95");
  });
  it("smaller_asset_set_retains_one_keyboard_entry", () => {
    const { container, rerender } = render(<CorrelationHeatmap result={ok} table={false} />);
    fireEvent.focus(container.querySelector('[data-row="4"][data-col="4"]')!);
    const updated = structuredClone(ok);
    updated.correlation.symbols = updated.correlation.symbols.slice(0, 2);
    updated.correlation.matrix = updated.correlation.matrix.slice(0, 2).map(row => row.slice(0, 2));
    rerender(<CorrelationHeatmap result={updated} table={false} />);
    expect(container.querySelectorAll('.c-heatmap__cell[tabindex="0"]').length).toBe(1);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
