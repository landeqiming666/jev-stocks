import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { TOAST_EVENT } from "../../app/events";
import { useAppStore } from "../../app/store";
import { dismissToast, getToasts } from "../../lib/toast-store";
import { FeedbackHost } from "./FeedbackHost";

afterEach(() => { cleanup(); useAppStore.getState().reset(); getToasts().forEach(item => dismissToast(item.id)); });
test("online_recovery_shows_one_toast", () => {
  render(<FeedbackHost><p>page</p></FeedbackHost>);
  fireEvent(window, new Event("offline"));
  fireEvent(window, new Event("online"));
  fireEvent(window, new Event("online"));
  expect(screen.getAllByText("已恢复联网")).toHaveLength(1);
});

test("strictmode_duplicate_hosts_use_one_root_listener_and_take_over_after_owner_unmount", () => {
  const first = render(<StrictMode><FeedbackHost><p>first</p></FeedbackHost></StrictMode>);
  const second = render(<StrictMode><FeedbackHost><p>second</p></FeedbackHost></StrictMode>);
  expect(document.querySelectorAll("#feedback-root")).toHaveLength(1);
  expect(document.querySelectorAll(".c-feedback-toasts")).toHaveLength(1);
  fireEvent(window, new CustomEvent(TOAST_EVENT, { detail: { tone: "ok", text: "saved" } }));
  expect(screen.getAllByText("saved")).toHaveLength(1);
  first.unmount();
  expect(document.querySelectorAll(".c-feedback-toasts")).toHaveLength(1);
  fireEvent(window, new CustomEvent(TOAST_EVENT, { detail: { tone: "danger", text: "failed" } }));
  expect(screen.getAllByText("failed")).toHaveLength(1);
  second.unmount();
  expect(document.querySelector("#feedback-root")).toBeNull();
  const count = getToasts().length;
  fireEvent(window, new CustomEvent(TOAST_EVENT, { detail: { tone: "error", text: "after cleanup" } }));
  expect(getToasts()).toHaveLength(count);
});

test("existing_feedback_root_is_reused_and_not_removed", () => {
  const root = document.createElement("div"); root.id = "feedback-root"; document.body.append(root);
  const view = render(<FeedbackHost><p>page</p></FeedbackHost>);
  expect(document.querySelectorAll("#feedback-root")).toHaveLength(1);
  view.unmount();
  expect(root.isConnected).toBe(true);
  expect(root.children).toHaveLength(0);
  root.remove();
});

test("host_rejects_malformed_event_and_does_not_create_or_dispose_store_client", () => {
  const dispose = vi.fn(), status = vi.fn(() => "ready" as const);
  act(() => useAppStore.setState({ client: { status, dispose } as never }));
  const view = render(<FeedbackHost coreStatusListener={async () => () => {}}><p>page</p></FeedbackHost>);
  for (const detail of [null, { tone: "error", text: 17 }, { tone: "other", text: "private" }, { tone: "success", text: " " }])
    fireEvent(window, new CustomEvent(TOAST_EVENT, { detail }));
  expect(getToasts()).toHaveLength(0);
  view.unmount();
  expect(dispose).not.toHaveBeenCalled();
});
