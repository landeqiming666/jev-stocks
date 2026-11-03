import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { Application } from "../../app/Application";
import { useAppStore } from "../../app/store";
import { createMockRpcClient } from "../../rpc";
import { dismissToast, getToasts } from "../../lib/toast-store";
import { feedback } from "../../i18n/zh-CN/feedback";

beforeEach(() => {
  vi.stubEnv("VITE_RPC", "tauri");
  window.location.hash = "#/today";
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false,
    addEventListener: vi.fn(), removeEventListener: vi.fn() }) });
  useAppStore.getState().reset();
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); getToasts().forEach(toast => dismissToast(toast.id)); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

test.each(["bootstrap", "dataStatus"] as const)("application_real_router_feedback_and_offline_%s_has_one_banner", async source => {
  const createClient = () => {
    const client = createMockRpcClient({ scenario: "today.offline", warn: () => {} });
    if (source === "dataStatus") client.setExample("app.bootstrap", "ready");
    client.setExample("decision.get", "overturn");
    return client;
  };
  render(<StrictMode><Application createClient={createClient} /></StrictMode>);
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  await screen.findByText(feedback.offline);
  expect(screen.getAllByText(feedback.offline)).toHaveLength(1);
  expect(document.querySelectorAll(".c-feedback-banners .c-banner--warn")).toHaveLength(1);
  expect(document.querySelectorAll(".l-notice, .p-today .c-banner--warn")).toHaveLength(0);
  expect(document.querySelectorAll("#feedback-root")).toHaveLength(1);
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
  const trigger = screen.getAllByRole("button", { name: "查看原文" })[0]!;
  trigger.focus(); fireEvent.click(trigger);
  await waitFor(() => expect(document.querySelector("mark")).not.toBeNull());
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.click(screen.getAllByRole("button", { name: "仍然成立" })[0]!);
  await screen.findByRole("heading", { name: "今天有 2 件事需要你看一眼" });
  expect(screen.getAllByText(feedback.offline)).toHaveLength(1);
});
