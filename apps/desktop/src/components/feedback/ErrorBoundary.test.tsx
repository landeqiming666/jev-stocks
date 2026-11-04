import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { feedbackRootOptions } from "../../lib/errors";
import { dismissToast, getToasts } from "../../lib/toast-store";
import { ErrorBoundary } from "./ErrorBoundary";

const rootOptions = { onCaughtError: feedbackRootOptions.onCaughtError, onRecoverableError: feedbackRootOptions.onRecoverableError };

afterEach(() => { cleanup(); getToasts().forEach(item => dismissToast(item.id)); vi.restoreAllMocks(); });
function Broken() { throw new Error("test-key-do-not-use at private-stack"); return null; }

test("error_boundary_shows_id_and_hides_stack", () => {
  render(<ErrorBoundary><Broken /></ErrorBoundary>, { onCaughtError: () => {} });
  expect(screen.getByText(/错误编号：[A-F0-9]{12}/)).toBeTruthy();
  expect(document.body.textContent).not.toContain("at ");
  expect(document.body.textContent).not.toContain("test-key-do-not-use");
});

test("copy_failure_is_visible_retry_recovers_and_unknown_error_is_not_logged", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const writeText = vi.fn().mockRejectedValue(new Error("private-copy-secret"));
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  let broken = true;
  function Child() { if (broken) throw new Error("test-key-do-not-use"); return <p>recovered</p>; }
  render(<StrictMode><ErrorBoundary><Child /></ErrorBoundary></StrictMode>, rootOptions);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "复制错误详情" })));
  expect(screen.getByRole("alert").textContent).toContain("复制失败");
  const diagnostic = JSON.parse(writeText.mock.calls[0]![0]);
  expect(diagnostic.requestId).toMatch(/^[A-F0-9]{12}$/);
  expect(Object.keys(diagnostic)).toEqual(["code", "requestId", "appVersion", "protocolVersion", "time"]);
  expect(document.body.textContent).not.toContain("private");
  expect(writeText.mock.calls[0]![0]).not.toContain("test-key-do-not-use");
  expect(log).not.toHaveBeenCalled();
  broken = false;
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(screen.getByText("recovered")).toBeTruthy();
});

test("successful_copy_contains_only_diagnostic_and_completion_after_unmount_is_ignored", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const view = render(<ErrorBoundary><Broken /></ErrorBoundary>, rootOptions);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "复制错误详情" })));
  expect(getToasts().map(item => item.text)).toEqual(["已复制错误详情"]);
  getToasts().forEach(item => dismissToast(item.id));
  let resolve: () => void = () => {};
  writeText.mockImplementation(() => new Promise<void>(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "复制错误详情" }));
  view.unmount();
  await act(async () => resolve());
  expect(getToasts()).toEqual([]);
});

test("custom_fallback_is_respected", () => {
  render(<ErrorBoundary fallback={<p>custom fallback</p>}><Broken /></ErrorBoundary>, rootOptions);
  expect(screen.getByText("custom fallback")).toBeTruthy();
});
