import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

afterEach(cleanup);

it("segmented_arrow_moves_selection", () => {
  function Controlled() {
    const [value, setValue] = useState("first");
    return <SegmentedControl name="window" label="Window" value={value}
      items={[{ value: "first", label: "First" }, { value: "second", label: "Second" }]}
      onChange={setValue} />;
  }
  render(<Controlled />);
  const radios = screen.getAllByRole("radio");
  radios[0]!.focus();
  fireEvent.keyDown(radios[0]!, { key: "ArrowRight" });
  expect(radios[1]!.getAttribute("aria-checked")).toBe("true");
  expect(radios[0]!.getAttribute("aria-checked")).toBe("false");
  expect(document.activeElement).toBe(radios[1]);
  expect(radios[0]!.tabIndex).toBe(-1);
  expect(radios[1]!.tabIndex).toBe(0);
});
