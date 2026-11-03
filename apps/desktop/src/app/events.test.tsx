import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { notifyToast, refresh, REFRESH_EVENT, TOAST_EVENT } from "./events";
import { useEscape } from "./useEscape";

afterEach(cleanup);
it("toast_and_refresh_events_have_stable_names_and_payloads", () => {
  const toast = vi.fn(), updated = vi.fn();
  window.addEventListener(TOAST_EVENT, toast); window.addEventListener(REFRESH_EVENT, updated);
  notifyToast("error", "test"); refresh("holdings");
  expect((toast.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({ tone: "error", text: "test" });
  expect((updated.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({ scope: "holdings" });
  window.removeEventListener(TOAST_EVENT, toast); window.removeEventListener(REFRESH_EVENT, updated);
});
it("escape_uses_latest_callback_respects_disabled_and_cleans_up", () => {
  function Probe({ handler, enabled = true }: { handler: () => void; enabled?: boolean }) {
    useEscape(handler, enabled); return null;
  }
  const first = vi.fn(), next = vi.fn();
  const view = render(<Probe handler={first} />);
  fireEvent.keyDown(document, { key: "Escape", isComposing: true });
  expect(first).not.toHaveBeenCalled();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(first).toHaveBeenCalledOnce();
  view.rerender(<Probe handler={next} />);
  fireEvent.keyDown(document, { key: "Escape" }); expect(next).toHaveBeenCalledOnce();
  view.rerender(<Probe handler={next} enabled={false} />);
  fireEvent.keyDown(document, { key: "Escape" }); expect(next).toHaveBeenCalledOnce();
  view.unmount(); fireEvent.keyDown(document, { key: "Escape" }); expect(next).toHaveBeenCalledOnce();
});
