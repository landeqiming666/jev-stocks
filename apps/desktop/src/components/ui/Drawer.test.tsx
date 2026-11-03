import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { PageFrame } from "../../shell/PageFrame";
import { Drawer } from "./Drawer";

afterEach(cleanup);

function Harness({ overlay }: { overlay: boolean }) {
  const [open, setOpen] = useState(false);
  const drawer = <Drawer open={open} overlay={overlay} titleId="drawer-title" onClose={() => setOpen(false)}>
    <h2 id="drawer-title" tabIndex={-1}>Drawer title</h2>
    <button>First</button><button>Last</button>
  </Drawer>;
  return <>
    <PageFrame asideOpen={open && !overlay} aside={overlay ? undefined : drawer} asideLabel="Evidence">
      <button onClick={() => setOpen(true)}>Open drawer</button>
      <button>Outside</button>
    </PageFrame>
    {overlay && drawer}
  </>;
}

it("drawer_overlay_traps_focus_and_restores", () => {
  render(<Harness overlay />);
  const trigger = screen.getByRole("button", { name: "Open drawer" });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog");
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(screen.getByText("Drawer title"));
  const first = screen.getByRole("button", { name: "First" });
  const last = screen.getByRole("button", { name: "Last" });
  last.focus();
  expect(fireEvent.keyDown(last, { key: "Tab" })).toBe(false);
  expect(document.activeElement).toBe(first);
  expect(fireEvent.keyDown(first, { key: "Tab", shiftKey: true })).toBe(false);
  expect(document.activeElement).toBe(last);
  fireEvent.keyDown(last, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("drawer_push_does_not_trap", () => {
  render(<Harness overlay={false} />);
  const trigger = screen.getByRole("button", { name: "Open drawer" });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog");
  expect(dialog.getAttribute("aria-modal")).toBe("false");
  expect(dialog.parentElement?.className).toBe("l-drawer");
  expect(dialog.classList.contains("l-drawer")).toBe(false);
  expect(document.querySelectorAll(".l-drawer")).toHaveLength(1);
  const last = screen.getByRole("button", { name: "Last" });
  last.focus();
  expect(fireEvent.keyDown(last, { key: "Tab" })).toBe(true);
  // jsdom 不执行浏览器的 Tab 默认动作；这里只断言组件未取消事件。
  fireEvent.keyDown(last, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});
