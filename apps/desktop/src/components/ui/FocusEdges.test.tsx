import { createRef, StrictMode, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { Drawer, Modal } from "./index";

afterEach(cleanup);

it.each(["drawer", "modal"] as const)("strictmode_%s_cleanup_re_setup_restores_original_trigger_and_reopens", kind => {
  function Harness() {
    const [open, setOpen] = useState(false);
    const Component = kind === "drawer" ? Drawer : Modal;
    return <><button onClick={() => setOpen(true)}>Open</button>
      {open && <Component open overlay titleId="title" onClose={() => setOpen(false)}>
        <h2 id="title">Title</h2><button>{common.cancel}</button><input aria-label="Value" />
      </Component>}
    </>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  const trigger = screen.getByRole("button", { name: "Open" });
  for (let attempt = 0; attempt < 2; attempt++) {
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(document.body);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.querySelectorAll(".c-modal-scrim, .c-drawer-scrim")).toHaveLength(0);
  }
});

it("modal_on_drawer_only_top_layer_escapes_and_restores_both_focus_destinations", () => {
  const drawerClose = vi.fn(), modalClose = vi.fn();
  function Harness() {
    const [drawer, setDrawer] = useState(false), [modal, setModal] = useState(false);
    return <><button onClick={() => setDrawer(true)}>Open drawer</button>
      {drawer && <Drawer open overlay titleId="drawer-title" onClose={() => { drawerClose(); setDrawer(false); }}>
        <h2 id="drawer-title">Evidence</h2><button onClick={() => setModal(true)}>Open modal</button>
        {modal && <Modal open titleId="modal-title" onClose={() => { modalClose(); setModal(false); }}>
          <h2 id="modal-title">Confirm</h2><button>{common.cancel}</button>
        </Modal>}
      </Drawer>}
    </>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  const trigger = screen.getByRole("button", { name: "Open drawer" });
  trigger.focus(); fireEvent.click(trigger);
  const modalTrigger = screen.getByRole("button", { name: "Open modal" });
  modalTrigger.focus(); fireEvent.click(modalTrigger);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: common.cancel }));
  fireEvent.click(document.querySelector(".c-drawer-scrim")!);
  expect(drawerClose).not.toHaveBeenCalled();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(modalClose).toHaveBeenCalledOnce();
  expect(drawerClose).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(modalTrigger);
  expect(document.querySelector(".c-modal-scrim")).toBeNull();
  expect(document.querySelector(".c-drawer-scrim")).not.toBeNull();
  fireEvent.keyDown(modalTrigger, { key: "Escape" });
  expect(drawerClose).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(trigger);
});

it("modal_traps_skips_disabled_prefers_input_and_handles_programmatic_focus", () => {
  const close = vi.fn(), ref = createRef<HTMLDivElement>();
  render(<><button>Outside</button><Modal ref={ref} open titleId="title" onClose={close}>
    <h2 id="title">Title</h2><button disabled>Disabled</button><input aria-label="Input" />
    <button>{common.cancel}</button><button hidden>Hidden</button>
  </Modal></>);
  const first = screen.getByRole("textbox"), last = screen.getByRole("button", { name: common.cancel });
  expect(document.activeElement).toBe(first);
  last.focus(); fireEvent.keyDown(last, { key: "Tab" });
  expect(document.activeElement).toBe(first);
  fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(last);
  screen.getByRole("button", { name: "Outside" }).focus();
  expect(document.activeElement).toBe(first);
  expect(ref.current).toBe(screen.getByRole("dialog"));
  fireEvent.keyDown(first, { key: "Escape", isComposing: true });
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(document.querySelector(".c-modal-scrim")!);
  expect(close).toHaveBeenCalledOnce();
});

it("empty_modal_uses_root_fallback_and_does_not_leak_listeners_after_unmount", () => {
  const close = vi.fn();
  const { unmount } = render(<Modal open titleId="title" onClose={close}><h2 id="title">Title</h2></Modal>);
  const dialog = screen.getByRole("dialog");
  expect(document.activeElement).toBe(dialog);
  expect(fireEvent.keyDown(dialog, { key: "Tab" })).toBe(false);
  expect(document.activeElement).toBe(dialog);
  unmount();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
});

it("open_layer_rerender_does_not_re_capture_focus_or_reset_it", () => {
  function Harness() {
    const [open, setOpen] = useState(false), [count, setCount] = useState(0);
    return <><button onClick={() => setOpen(true)}>Open</button><Drawer open={open} overlay titleId="title" onClose={() => setOpen(false)}>
      <h2 id="title">Title</h2><button onClick={() => setCount(count + 1)}>Increment {count}</button>
    </Drawer></>;
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Open" });
  trigger.focus(); fireEvent.click(trigger);
  const button = screen.getByRole("button", { name: "Increment 0" });
  button.focus(); fireEvent.click(button);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Increment 1" }));
  fireEvent.keyDown(button, { key: "Escape" });
  expect(document.activeElement).toBe(trigger);
});

it("drawer_push_allows_outside_focus_and_overlay_scrim_closes", () => {
  const onClose = vi.fn();
  const { rerender } = render(<><button>Outside</button><Drawer open overlay={false} titleId="title" onClose={onClose}>
    <h2 id="title">Title</h2><button>Inside</button>
  </Drawer></>);
  screen.getByRole("button", { name: "Outside" }).focus();
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Outside" }));
  rerender(<Drawer open overlay titleId="title" onClose={onClose}><h2 id="title">Title</h2></Drawer>);
  fireEvent.click(document.querySelector(".c-drawer-scrim")!);
  expect(onClose).toHaveBeenCalledOnce();
});

it("drawer_missing_title_is_rejected_without_leaving_a_layer", () => {
  expect(() => render(<Drawer open overlay titleId="" onClose={() => {}}>Content</Drawer>)).toThrow(/titleId/);
  expect(document.querySelector(".c-drawer-scrim")).toBeNull();
});

it("initially_nested_modal_does_not_replace_drawer_origin_with_modal_control", () => {
  const trigger = document.createElement("button");
  document.body.append(trigger); trigger.focus();
  const { rerender, unmount } = render(<Drawer open overlay titleId="drawer-title" onClose={() => {}}>
    <h2 id="drawer-title">Evidence</h2><Modal open titleId="modal-title" onClose={() => {}}>
      <h2 id="modal-title">Confirm</h2><input aria-label="Value" />
    </Modal>
  </Drawer>);
  expect(document.activeElement).toBe(screen.getByRole("textbox"));
  rerender(<Drawer open overlay titleId="drawer-title" onClose={() => {}}><h2 id="drawer-title">Evidence</h2></Drawer>);
  expect(document.activeElement).toBe(screen.getByText("Evidence"));
  unmount();
  expect(document.activeElement).toBe(trigger);
  trigger.remove();
});

it("unmounting_drawer_with_open_modal_restores_outer_trigger", () => {
  function Harness() {
    const [drawer, setDrawer] = useState(false), [modal, setModal] = useState(false);
    return <><button onClick={() => setDrawer(true)}>Outer trigger</button>
      {drawer && <Drawer open overlay titleId="drawer-title" onClose={() => setDrawer(false)}>
        <h2 id="drawer-title">Drawer</h2><button onClick={() => setModal(true)}>Modal trigger</button>
        {modal && <Modal open titleId="modal-title" onClose={() => setDrawer(false)}>
          <h2 id="modal-title">Modal</h2><button>Close all</button>
        </Modal>}
      </Drawer>}
    </>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  const trigger = screen.getByRole("button", { name: "Outer trigger" });
  trigger.focus(); fireEvent.click(trigger);
  const modalTrigger = screen.getByRole("button", { name: "Modal trigger" });
  modalTrigger.focus(); fireEvent.click(modalTrigger);
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryAllByRole("dialog")).toHaveLength(0);
  expect(document.activeElement).toBe(trigger);
});
