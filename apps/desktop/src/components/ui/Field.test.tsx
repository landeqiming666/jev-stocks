import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Field } from "./Field";

afterEach(cleanup);

it("field_error_links_aria_describedby", () => {
  render(<>
    <span id="existing-help">Existing description</span>
    <Field id="statement" label="逻辑" help="Help" error="逻辑内容不能为空">
      <input aria-describedby="existing-help" />
    </Field>
  </>);
  const input = screen.getByRole("textbox");
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(screen.getByLabelText("逻辑")).toBe(input);
  const descriptionIds = input.getAttribute("aria-describedby")!.split(/\s+/);
  expect(descriptionIds).toContain("existing-help");
  expect(descriptionIds).toContain(screen.getByRole("alert").id);
  expect(descriptionIds).toContain(screen.getByText("Help").id);
});

it("field_count_trims_whitespace", () => {
  render(<Field id="statement" label="逻辑" count={{ value: 3, max: 500 }}>
    <textarea value="   " readOnly />
  </Field>);
  expect(screen.queryByText("0 / 500")).not.toBeNull();
});
