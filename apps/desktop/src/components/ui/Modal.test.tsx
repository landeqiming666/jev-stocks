import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { Modal } from "./Modal";

afterEach(cleanup);

it("modal_escape_and_overlay_close", () => {
  const onClose = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(false);
    return <>
      <button onClick={() => setOpen(true)}>Open modal</button>
      <Modal open={open} titleId="modal-title" onClose={() => { onClose(); setOpen(false); }}>
        <h2 id="modal-title">Modal title</h2>
        <button>{common.cancel}</button>
      </Modal>
    </>;
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Open modal" });
  trigger.focus();
  fireEvent.click(trigger);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
  fireEvent.click(trigger);
  const scrim = document.querySelector(".l-scrim");
  expect(scrim).not.toBeNull();
  fireEvent.click(scrim!);
  expect(onClose).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});
