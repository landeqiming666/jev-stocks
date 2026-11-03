import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { Heatmap, BarList, Probability, Progress, Table } from "./index";

afterEach(cleanup);

it.each([[[1, NaN], [0, 1]], [[1, Infinity], [0, 1]], [[1, 1.01], [0, 1]], [[1, -1.01], [0, 1]], [[1]], [[1, 0], [0]]].map(matrix => ({ matrix })))(
  "heatmap_rejects_nonfinite_out_of_range_and_nonsquare_matrices_%j", ({ matrix }) => {
    render(<Heatmap symbols={["ZZAR", "ZZCL"]} matrix={matrix} label="Correlation" />);
    expect(screen.getByText(common.chartInvalid)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  },
);

it("heatmap_rejects_sparse_cells", () => {
  render(<Heatmap symbols={["ZZAR", "ZZCL"]} matrix={[Array<number>(2), [0, 1]]} label="Correlation" />);
  expect(screen.queryByText(common.chartInvalid)).not.toBeNull();
});

it("heatmap_null_hatch_ids_titles_negative_mix_and_diagonal_are_accessible", () => {
  render(<><Heatmap symbols={["ZZAR", "ZZCL"]} matrix={[[1, null], [-1, 1]]} label="First" />
    <Heatmap symbols={["ZZFD"]} matrix={[[null]]} label="Second" /></>);
  const first = screen.getByRole("img", { name: "First" });
  const titles = [...first.querySelectorAll("title")].map(node => node.textContent);
  expect(titles).toContain(common.chartCellTitle("ZZAR", "ZZCL", null));
  expect(titles).toContain(common.chartCellTitle("ZZCL", "ZZAR", -1));
  expect(first.querySelector(".is-neg rect")!.getAttribute("style")).toContain("70%");
  expect(first.querySelectorAll(".is-diag")).toHaveLength(2);
  const patterns = [...document.querySelectorAll("pattern")].map(node => node.id);
  expect(new Set(patterns).size).toBe(2);
  const fills = [...document.querySelectorAll(".c-heatmap__null")].map(node => node.getAttribute("fill"));
  expect(fills).toEqual(patterns.map(id => `url(#${id})`));
});

it("chart_empty_data_and_same_data_table_are_visible", () => {
  render(<><Heatmap symbols={[]} matrix={[]} label="Correlation" />
    <Table label="Correlation table"><tbody><tr><th scope="row">ZZAR</th><td>1.00</td></tr></tbody></Table></>);
  expect(screen.getByText(common.chartEmpty)).toBeTruthy();
  expect(screen.getByRole("table", { name: "Correlation table" }).textContent).toContain("1.00");
});

it("barlist_clamps_fraction_and_handles_infinities_without_nan_styles", () => {
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    const { container } = render(<BarList label="Variance" items={[-1, 0.46, 2, Infinity, -Infinity].map((value, index) => ({ label: String(index), value }))} />);
    expect([...container.querySelectorAll(".c-barlist__fill")].map(node => node.getAttribute("style"))).toEqual([
      "--w: 0%;", "--w: 46%;", "--w: 100%;", "--w: 0%;", "--w: 0%;",
    ]);
    expect(container.textContent).toContain("46.0%");
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    expect(screen.getByRole("list", { name: "Variance" })).toBeTruthy();
  } finally { warning.mockRestore(); }
});

it.each([[NaN, 100, 0, 100], [Infinity, 10, 0, 10], [-1, 10, 0, 10], [99, 10, 10, 10], [1, 0, 0, 0], [1, NaN, 0, 0], [1, Infinity, 0, 0]])(
  "progress_normalizes_%s_%s", (value, max, now, total) => {
    render(<Progress label="Progress" value={value} max={max} />);
    const progress = screen.getByRole("progressbar");
    expect(progress.getAttribute("aria-valuenow")).toBe(String(now));
    expect(progress.getAttribute("aria-valuemax")).toBe(String(total));
    expect(progress.getAttribute("aria-valuemin")).toBe("0");
    expect(progress.parentElement!.innerHTML).not.toMatch(/NaN|Infinity/);
    const width = Number(progress.querySelector("span")!.style.getPropertyValue("--w").replace("%", ""));
    expect(width).toBeGreaterThanOrEqual(0);
    expect(width).toBeLessThanOrEqual(100);
  },
);

it.each([NaN, Infinity, -0.1, 1.1])("probability_invalid_%s_is_missing", value => {
  render(<Probability value={value} />);
  expect(screen.getByTitle(common.probabilityTitle).textContent).toBe(common.invalidValue);
});
