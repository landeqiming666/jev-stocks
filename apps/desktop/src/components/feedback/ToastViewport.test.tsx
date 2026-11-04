import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode, useRef, useState } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { dismissToast, getToasts, pushToast } from "../../lib/toast-store";
import { ToastViewport } from "./ToastViewport";
import { Button, Drawer, Menu, Modal } from "../ui";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); getToasts().forEach(item => dismissToast(item.id)); vi.useRealTimers(); });

test("success_toast_dismisses_after_4000ms", () => {
  pushToast({ tone: "success", text: "saved" });
  render(<ToastViewport />);
  expect(screen.getByRole("status").textContent).toContain("saved");
  act(() => vi.advanceTimersByTime(3999));
  expect(screen.getByText("saved")).toBeTruthy();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.queryByText("saved")).toBeNull();
});

test("error_toast_does_not_auto_dismiss", () => {
  pushToast({ tone: "error", text: "failed" });
  render(<ToastViewport />);
  act(() => vi.advanceTimersByTime(10000));
  expect(screen.getByRole("alert").textContent).toContain("failed");
});

test("dedupe_resets_u01_timer_and_escape_dismisses_newest_only", () => {
  render(<StrictMode><ToastViewport /></StrictMode>);
  act(() => { pushToast({ tone: "success", text: "saved" }); vi.advanceTimersByTime(900); pushToast({ tone: "success", text: "saved" }); });
  act(() => vi.advanceTimersByTime(3100));
  expect(screen.getByText("saved")).toBeTruthy();
  act(() => vi.advanceTimersByTime(900));
  expect(screen.queryByText("saved")).toBeNull();
  act(() => { pushToast({ tone: "error", text: "first" }); pushToast({ tone: "error", text: "second" }); });
  fireEvent.keyDown(document.body, { key: "Escape" });
  expect(screen.queryByText("second")).toBeNull();
  expect(screen.getByText("first")).toBeTruthy();
});

function Layers() {
  const [drawer, setDrawer] = useState(true), [modal, setModal] = useState(true), [menu, setMenu] = useState(true);
  const trigger = useRef<HTMLButtonElement>(null);
  return <><ToastViewport /><Drawer open={drawer} overlay titleId="drawer-title" onClose={() => setDrawer(false)}>
    <h2 id="drawer-title">Drawer</h2><Button>Drawer button</Button>
  </Drawer><Modal open={modal} titleId="modal-title" onClose={() => setModal(false)}>
    <h2 id="modal-title">Modal</h2><Button ref={trigger} id="menu-trigger">Menu trigger</Button>
    {menu && <Menu triggerRef={trigger} items={[{ id: "one", label: "Menu item" }]} onSelect={() => {}} onClose={() => setMenu(false)} />}
  </Modal></>;
}

test("strictmode_escape_closes_menu_modal_drawer_then_toast_in_order", () => {
  pushToast({ tone: "error", text: "toast" });
  render(<StrictMode><Layers /></StrictMode>);
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(screen.getAllByRole("dialog")).toHaveLength(2);
  expect(screen.getByText("toast")).toBeTruthy();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(screen.getByText("toast")).toBeTruthy();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByText("toast")).toBeTruthy();
  fireEvent.keyDown(document.body, { key: "Escape" });
  expect(screen.queryByText("toast")).toBeNull();
});

test("prevented_and_composing_escape_do_not_close_and_listener_cleans_up", () => {
  pushToast({ tone: "error", text: "toast" });
  const view = render(<ToastViewport />);
  fireEvent.keyDown(document.body, { key: "Escape", isComposing: true });
  const prevented = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
  prevented.preventDefault(); fireEvent(document.body, prevented);
  expect(screen.getByText("toast")).toBeTruthy();
  view.unmount();
  fireEvent.keyDown(document.body, { key: "Escape" });
  expect(getToasts()).toHaveLength(1);
});
