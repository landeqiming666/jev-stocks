import { createRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Menu } from "./Menu";

afterEach(cleanup);

it("menu_escape_closes_and_restores_focus", () => {
  const triggerRef = createRef<HTMLButtonElement>();
  const onClose = vi.fn();
  render(<>
    <button ref={triggerRef}>Open menu</button>
    <Menu items={[{ id: "save", label: "Save" }]} triggerRef={triggerRef}
      onClose={onClose} onSelect={vi.fn()} />
  </>);
  const item = screen.getByRole("menuitem");
  item.focus();
  fireEvent.keyDown(item, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(document.activeElement).toBe(triggerRef.current);
});
