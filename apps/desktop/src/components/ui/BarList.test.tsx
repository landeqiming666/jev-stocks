import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BarList } from "./BarList";

afterEach(cleanup);

it("bar_list_nonfinite_value_is_safe", () => {
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    render(<BarList items={[{ label: "First", value: NaN }]} label="Variance" />);
    const list = screen.getByRole("list", { name: "Variance" });
    expect(screen.queryByText("0%")).not.toBeNull();
    expect(list.textContent).not.toContain("NaN");
    expect(list.querySelector(".c-barlist__fill")?.getAttribute("style")).toContain("0%");
    expect(warning).toHaveBeenCalled();
  } finally {
    warning.mockRestore();
  }
});
