import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { BudgetBar } from "./BudgetBar";

afterEach(cleanup);
it("budget_bar_turns_warn_at_80_percent", () => {
  const { container } = render(<BudgetBar usedTokens={1600000} limitTokens={2000000} resetAt="2026-11-03T00:00:00Z" />);
  expect(container.querySelector(".is-warn")).toBeTruthy();
  expect(screen.getByText(/预算已使用 80%/)).toBeTruthy();
});
it("budget_bar_turns_danger_at_limit", () => {
  const { container } = render(<BudgetBar usedTokens={2000000} limitTokens={2000000} resetAt="2026-11-03T00:00:00Z" />);
  expect(container.querySelector(".is-danger")).toBeTruthy();
  expect(screen.getByText("预算已用完")).toBeTruthy();
});
