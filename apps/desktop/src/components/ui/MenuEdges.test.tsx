import { createRef, StrictMode, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Menu, Modal, Drawer } from "./index";
import { PageFrame } from "../../shell/PageFrame";

afterEach(cleanup);

it("menu_arrows_home_end_wrap_skip_disabled_and_select_then_close", () => {
  const ref = createRef<HTMLButtonElement>(), select = vi.fn(), close = vi.fn();
  render(<><button ref={ref}>Trigger</button><Menu triggerRef={ref} onClose={close} onSelect={select}
    items={[{ id: "a", label: "A", icon: "check" }, { id: "b", label: "B", disabled: true }, { id: "c", label: "C", danger: true }]} /></>);
  const a = screen.getByRole("menuitem", { name: "A" }), c = screen.getByRole("menuitem", { name: "C" });
  expect(document.activeElement).toBe(a);
  for (const [key, from, to] of [["ArrowDown", a, c], ["ArrowDown", c, a], ["ArrowUp", a, c], ["Home", c, a], ["End", a, c]] as const) {
    fireEvent.keyDown(from, { key });
    expect(document.activeElement).toBe(to);
  }
  fireEvent.click(screen.getByRole("menuitem", { name: "B" }));
  expect(select).not.toHaveBeenCalled();
  fireEvent.click(c);
  expect(select).toHaveBeenCalledWith("c");
  expect(close).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(ref.current);
  expect(c.classList.contains("u-danger")).toBe(true);
});

it("menu_all_disabled_empty_and_nullable_trigger_do_not_throw", () => {
  const ref = createRef<HTMLButtonElement>(), root = createRef<HTMLDivElement>(), close = vi.fn();
  const { rerender } = render(<StrictMode><Menu ref={root} triggerRef={ref} onClose={close} onSelect={vi.fn()}
    items={[{ id: "a", label: "A", disabled: true }]} /></StrictMode>);
  expect(document.activeElement).toBe(root.current);
  for (const key of ["ArrowUp", "ArrowDown", "Home", "End"]) fireEvent.keyDown(root.current!, { key });
  fireEvent.keyDown(root.current!, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
  rerender(<Menu ref={root} triggerRef={ref} onClose={close} onSelect={vi.fn()} items={[]} />);
  expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
});

it("modal_above_existing_menu_owns_escape_and_restores_menu_then_trigger", () => {
  const trigger = createRef<HTMLButtonElement>(), menuClose = vi.fn();
  function Harness() {
    const [modal, setModal] = useState(true);
    return <><button ref={trigger}>Trigger</button><Menu triggerRef={trigger} onClose={menuClose}
      onSelect={() => {}} items={[{ id: "a", label: "A" }]} />
      <Modal open={modal} titleId="title" onClose={() => setModal(false)}>
        <h2 id="title">Modal</h2><button>Cancel</button>
      </Modal></>;
  }
  render(<Harness />);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(menuClose).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(screen.getByRole("menuitem"));
  fireEvent.keyDown(document.activeElement!, { key: "Tab" });
  expect(menuClose).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(trigger.current);
});

it("main_menu_above_open_pageframe_push_drawer_focuses_navigates_and_escapes_alone", () => {
  const trigger = createRef<HTMLButtonElement>(), drawerClose = vi.fn(), menuClose = vi.fn();
  function Harness() {
    const [menu, setMenu] = useState(false);
    return <PageFrame asideOpen aside={<Drawer open overlay={false} titleId="drawer-title" onClose={drawerClose}>
      <h2 id="drawer-title">Drawer</h2><button>Drawer action</button>
    </Drawer>}>
      <button ref={trigger} onClick={() => setMenu(true)}>Menu trigger</button>
      {menu && <Menu triggerRef={trigger} onClose={() => { menuClose(); setMenu(false); }} onSelect={() => {}}
        items={[{ id: "a", label: "A" }, { id: "b", label: "B", disabled: true }, { id: "c", label: "C" }]} />}
    </PageFrame>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  trigger.current!.focus(); fireEvent.click(trigger.current!);
  const first = screen.getByRole("menuitem", { name: "A" }), last = screen.getByRole("menuitem", { name: "C" });
  expect(document.activeElement).toBe(first);
  for (const [key, expected] of [["ArrowDown", last], ["Home", first], ["End", last]] as const) {
    fireEvent.keyDown(document.activeElement!, { key });
    expect(document.activeElement).toBe(expected);
  }
  fireEvent.keyDown(last, { key: "Escape" });
  expect(menuClose).toHaveBeenCalledOnce();
  expect(drawerClose).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", { name: "Drawer" })).toBeTruthy();
  expect(screen.queryByRole("menu")).toBeNull();
  expect(document.activeElement).toBe(trigger.current);
});
