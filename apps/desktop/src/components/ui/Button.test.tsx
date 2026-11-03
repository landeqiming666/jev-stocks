import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Button } from "./Button";

afterEach(cleanup);

it("button_loading_sets_aria_busy", () => {
  render(<Button loading>立即扫描</Button>);
  const button = screen.getByRole("button", { name: "立即扫描" });
  expect(button.getAttribute("aria-busy")).toBe("true");
  expect(button.textContent).toBe("立即扫描");
  expect(button.getAttribute("type")).toBe("button");
  expect(button.querySelector("svg")).not.toBeNull();
});
