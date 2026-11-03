import { createRef } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Icon, type IconName } from "./index";

afterEach(cleanup);

it("all_23_icon_paths_and_svg_attributes_match_the_readonly_prototype", () => {
  const context = { window: { Proto: {} as { iconNames: IconName[]; icon: (name: IconName) => string } } };
  runInNewContext(readFileSync(resolve("../../design/prototype/js/icons.js"), "utf8"), context);
  expect(context.window.Proto.iconNames).toHaveLength(23);
  const ref = createRef<SVGSVGElement>();
  for (const name of context.window.Proto.iconNames) {
    const { unmount } = render(<Icon ref={ref} name={name} />);
    const reference = document.createElement("div");
    reference.innerHTML = context.window.Proto.icon(name);
    expect(ref.current!.innerHTML).toBe(reference.querySelector("svg")!.innerHTML);
    for (const attribute of ["viewBox", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "focusable"]) {
      expect(ref.current!.getAttribute(attribute)).toBe(reference.querySelector("svg")!.getAttribute(attribute));
    }
    expect(ref.current!.getAttribute("aria-hidden")).toBe("true");
    expect(ref.current!.hasAttribute("tabindex")).toBe(false);
    unmount();
  }
});

it("labeled_icon_is_named_and_20px_class_is_preserved", () => {
  const ref = createRef<SVGSVGElement>();
  render(<Icon ref={ref} name="info" label="Information" size={20} />);
  expect(ref.current!.getAttribute("role")).toBe("img");
  expect(ref.current!.getAttribute("aria-label")).toBe("Information");
  expect(ref.current!.hasAttribute("aria-hidden")).toBe(false);
  expect(ref.current!.classList.contains("c-icon--20")).toBe(true);
  expect(ref.current!.hasAttribute("data-ui")).toBe(true);
});
