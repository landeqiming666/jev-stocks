import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { Probability } from "./Probability";

afterEach(cleanup);

it("probability_formats_two_decimals", () => {
  render(<Probability value={0.9} />);
  expect(screen.queryByText("0.90")).not.toBeNull();
  expect(screen.getByTitle(common.probabilityTitle).textContent).toBe("0.90");
});
