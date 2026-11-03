import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Heatmap } from "./Heatmap";

afterEach(cleanup);

it("heatmap_uses_max_70_percent_mix", () => {
  render(<Heatmap symbols={["ZZAR", "ZZCL"]} matrix={[[1, 1], [1, 1]]} label="Correlation" />);
  const cell = screen.getByRole("img").querySelector('[data-row="0"][data-col="1"] rect');
  expect(cell).not.toBeNull();
  expect(cell!.getAttribute("style")).toContain("70%");
});
