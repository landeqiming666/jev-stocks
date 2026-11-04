import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

afterEach(cleanup);
it("nav_marks_only_current_route", async () => {
  const { NavRail } = await import("./NavRail");
  render(<NavRail route="holdings" />);
  const current = screen.getAllByRole("link").filter(el => el.getAttribute("aria-current") === "page");
  expect(current).toHaveLength(1);
  expect(current[0]?.textContent).toBe("持仓");
});
