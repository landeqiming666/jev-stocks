import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { VerdictChip } from "./VerdictChip";

afterEach(cleanup);

it("verdict_chip_has_text_and_icon", () => {
  render(<VerdictChip kind="overturn" />);
  const chip = screen.queryByText(common.verdict.overturn);
  expect(chip).not.toBeNull();
  expect(chip!.className).toBe("c-verdict c-verdict--over");
  expect(chip!.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
});
