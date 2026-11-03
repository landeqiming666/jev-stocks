import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useAppStore } from "../../app/store";
import { RpcError, type Inbox } from "../../rpc";
import TodayPage from "./index";
import { example, pendingInbox, readyBoot, testClient } from "./test-support";

beforeEach(() => {
  useAppStore.getState().reset();
  window.location.hash = "#/today";
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false,
    addEventListener: vi.fn(), removeEventListener: vi.fn() }) });
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); vi.restoreAllMocks(); });
function mount(inbox = pendingInbox()) {
  const fake = testClient(inbox);
  useAppStore.setState({ client: fake.client, bootstrap: { status: "ready", value: readyBoot(), error: null } });
  render(<TodayPage />);
  return fake;
}
test("today_pending_renders_three_cards_in_required_order", async () => {
  mount();
  await screen.findByRole("heading", { level: 1, name: "今天有 3 件事需要你看一眼" });
  const cards = screen.getAllByRole("article");
  expect(cards).toHaveLength(3);
  expect(cards.map(card => card.querySelector(".c-verdict")?.textContent)).toEqual(["推翻", "推翻", "削弱"]);
  expect(cards.map(card => card.querySelector(".c-prob")?.textContent)).toEqual(["0.93", "0.92", "0.74"]);
});
test("today_empty_states_checked_counts", async () => {
  mount(example<Inbox>("inbox.list", "empty"));
  await screen.findByRole("heading", { level: 1, name: "今天没有需要处理的变化" });
  expect(screen.getByText(/已检查 4 只标的、6 份披露、17 个段落/)).toBeTruthy();
});
test("today_uncertain_not_counted_in_n", async () => {
  mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  const summary = screen.getByText("系统拿不准的 2 条");
  expect(summary.closest("details")?.open).toBe(false);
});
test("today_scan_failed_keeps_last_items", async () => {
  const inbox = example<Inbox>("inbox.list", "scan_failed");
  mount(inbox);
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.getByRole("alert").textContent).toContain(inbox.lastScan!.error!.message);
});
test("today_title_only_marks_evidence", async () => {
  const inbox = pendingInbox(); inbox.items[0] = { ...inbox.items[0]!, contentStatus: "title_only" };
  mount(inbox);
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  expect(within(screen.getAllByRole("article")[0]!).getByText(/仅依据标题：/)).toBeTruthy();
});
test("today_act_moves_item_to_processed", async () => {
  const inbox = pendingInbox(); inbox.processed = [];
  const fake = mount(inbox);
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  fireEvent.click(within(screen.getAllByRole("article")[0]!).getByRole("button", { name: "仍然成立" }));
  await screen.findByRole("heading", { name: "今天有 2 件事需要你看一眼" });
  expect(screen.getByText("已处理（1）")).toBeTruthy();
  expect(fake.call.mock.calls.filter(([method]) => method === "decision.act")).toHaveLength(1);
});
test("today_act_failure_restores_item", async () => {
  const fake = mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  const toast = vi.fn(); window.addEventListener("sentinel:toast", toast);
  fake.call.mockRejectedValueOnce(new RpcError("INTERNAL", "synthetic failure"));
  fireEvent.click(screen.getAllByRole("button", { name: "仍然成立" })[0]!);
  await waitFor(() => expect(toast).toHaveBeenCalledOnce());
  expect(screen.getAllByRole("article")).toHaveLength(3);
  window.removeEventListener("sentinel:toast", toast);
});

test("today_production_hash_does_not_replace_store_client_data", async () => {
  vi.stubEnv("VITE_RPC", "tauri");
  window.location.hash = "#/today?state=empty&drawer=processed";
  mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  expect(screen.queryByRole("dialog")).toBeNull();
  vi.unstubAllEnvs();
});
test("today_action_success_focuses_next_heading_and_failure_restores_trigger", async () => {
  const fake = mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  const nextId = pendingInbox().items[1]!.decisionId;
  const first = screen.getAllByRole("button", { name: "仍然成立" })[0]!;
  first.focus(); fireEvent.click(first);
  await waitFor(() => expect(document.activeElement?.id).toBe(`t-${nextId}`));
  const retry = screen.getAllByRole("button", { name: "仍然成立" })[0]!;
  fake.call.mockRejectedValueOnce(new RpcError("INTERNAL", "failure"));
  retry.focus(); fireEvent.click(retry);
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(2));
  expect(document.activeElement?.textContent).toBe("仍然成立");
});
test("today_unconfigured_offline_prevent_scan_and_refresh_uses_current_configuration", async () => {
  const fake = mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  act(() => useAppStore.setState({ bootstrap: { status: "ready", value: { ...readyBoot(),
    configured: { jevKey: false, secEmail: false } }, error: null } }));
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
  act(() => useAppStore.setState({ bootstrap: { status: "ready", value: { ...readyBoot(), offline: true }, error: null } }));
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
  expect(fake.call.mock.calls.some(([method]) => method === "scan.start")).toBe(false);
});
test("today_demo_unconfigured_keeps_three_pending_one_uncertain_and_evidence", async () => {
  const inbox = pendingInbox(); inbox.uncertain = inbox.uncertain.slice(0, 1);
  const fake = testClient(inbox), boot = { ...readyBoot(), demoDataLoaded: true, configured: { jevKey: false, secEmail: false } };
  useAppStore.setState({ client: fake.client, bootstrap: { status: "ready", value: boot, error: null } });
  render(<TodayPage />);
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.getByText("系统拿不准的 1 条")).toBeTruthy();
  expect(screen.getByText("请先填写 Jev 密钥和 SEC 联系邮箱。")).toBeTruthy();
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
  screen.getAllByRole("button", { name: "查看原文" })[0]!.focus();
  fireEvent.click(screen.getAllByRole("button", { name: "查看原文" })[0]!);
  await waitFor(() => expect(document.querySelector("mark.c-evidence-mark")?.textContent).toBe(inbox.items[0]!.evidence.text));
  expect(fake.call.mock.calls.some(([method]) => method === "scan.start")).toBe(false);
});
test("today_clearing_key_preserves_cached_list_and_actions", async () => {
  mount();
  await screen.findByRole("heading", { name: "今天有 3 件事需要你看一眼" });
  act(() => useAppStore.setState({ bootstrap: { status: "ready", value: { ...readyBoot(), configured: { jevKey: false, secEmail: true } }, error: null } }));
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect((screen.getAllByRole("button", { name: "仍然成立" })[0] as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole("button", { name: "立即扫描" }) as HTMLButtonElement).disabled).toBe(true);
});
test("today_only_first_five_cards_visible_and_remaining_group_expands", async () => {
  const inbox = pendingInbox();
  inbox.items = Array.from({ length: 7 }, (_, index) => ({ ...inbox.items[0]!, decisionId: `01JC8Z5V3Q00000000000095Z${index}`, headline: 0.9 - index / 100 }));
  mount(inbox);
  await screen.findByRole("heading", { name: "今天有 7 件事需要你看一眼" });
  expect(screen.getAllByRole("article")).toHaveLength(5);
  const group = screen.getByText("其余 2 条").closest("details")!;
  group.open = true; fireEvent(group, new Event("toggle"));
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(7));
});
