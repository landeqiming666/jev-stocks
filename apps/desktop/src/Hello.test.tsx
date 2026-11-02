import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Hello } from "./Hello";

describe("Hello", () => {
  it("renders the product name as a heading", () => {
    render(<Hello />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("投资逻辑哨兵");
  });
});
