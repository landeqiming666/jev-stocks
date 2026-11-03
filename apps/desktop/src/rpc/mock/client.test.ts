import { afterEach, expect, test, vi } from "vitest";
import type { MethodName, ParamsOf } from "../generated/methods";
import { SCENARIOS } from "../../mocks/scenarios";
import { MOCK_EXAMPLES, MOCK_NOTIFICATIONS } from "../generated/mock-data";
import { waitFor } from "../test-fixtures";

afterEach(() => { vi.useRealTimers(); });

test("mock_today_pending_returns_inbox_pending", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ scenario: "today.pending" });
  expect((await client.call("inbox.list", {})).summary.pendingCount).toBe(3);
  client.dispose();
});

test("known_method_without_scenario_mapping_uses_first_success", async () => {
  const { createMockRpcClient } = await import("./client");
  const warn = vi.fn(), client = createMockRpcClient({ scenario: "today.pending", warn });
  for (let i = 0; i < 2; i++) {
    expect(await client.call("settings.get", {})).toEqual(MOCK_EXAMPLES["settings.get"].find(e => "result" in e)?.result);
  }
  expect(warn).toHaveBeenCalledExactlyOnceWith("mock: scenario fallback for settings.get");
  client.dispose();
});

test("all_page_and_drawer_scenarios_reference_existing_examples", () => {
  expect(Object.keys(SCENARIOS)).toHaveLength(49);
  for (const scenario of Object.values(SCENARIOS)) {
    for (const [method, name] of Object.entries(scenario.examples)) {
      expect(MOCK_EXAMPLES[method as MethodName].some(e => e.name === name)).toBe(true);
    }
  }
});

test("all_40_methods_have_default_successful_response", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ scenario: "v1.default", warn: vi.fn() });
  for (const method of Object.keys(MOCK_EXAMPLES) as MethodName[]) {
    const example = MOCK_EXAMPLES[method].find(e => "result" in e)!;
    const params = JSON.parse(JSON.stringify(example.params)) as ParamsOf<MethodName>;
    const result = await client.call(method, params);
    expect(result).toEqual(example.result);
  }
  client.dispose();
});

test("scripted_error_and_results_do_not_mutate_contract_examples", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ scenario: "today.pending" });
  const before = JSON.stringify(MOCK_EXAMPLES);
  const first = await client.call("inbox.list", {}); first.summary.pendingCount = 99;
  expect((await client.call("inbox.list", {})).summary.pendingCount).toBe(3);
  client.setExample("inbox.list", "empty");
  expect((await client.call("inbox.list", {})).summary.pendingCount).toBe(0);
  client.setExample("thesis.create", "empty");
  await expect(client.call("thesis.create", { instrumentId: "us:ZZAR", statement: "" })).rejects.toMatchObject({ code: "INVALID_ARGUMENT", retryable: false });
  expect(JSON.stringify(MOCK_EXAMPLES)).toBe(before); client.dispose();
});

test.each(["timeout", "abort"] as const)("delayed_mock_supports_%s_without_late_delivery", async kind => {
  vi.useFakeTimers();
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ delayMs: 100 }), controller = new AbortController();
  const promise = client.call("inbox.list", {}, { timeoutMs: 10, signal: controller.signal });
  const assertion = expect(promise).rejects.toMatchObject({ code: kind === "timeout" ? "TIMEOUT" : "CANCELLED" });
  await waitFor();
  if (kind === "abort") controller.abort(); else await vi.advanceTimersByTimeAsync(10);
  await assertion; await vi.advanceTimersByTimeAsync(100);
  expect(vi.getTimerCount()).toBe(0); client.dispose();
});

test("notification_injection_supports_defaults_overrides_and_multiple_subscribers", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({}), one = vi.fn(), two = vi.fn();
  const off = client.subscribe("scan.progress", one); client.subscribe("scan.progress", two);
  client.injectNotification("scan.progress");
  expect(one).toHaveBeenCalledWith(MOCK_NOTIFICATIONS["scan.progress"]);
  off(); client.injectNotification("scan.progress", { ...MOCK_NOTIFICATIONS["scan.progress"], done: 12 });
  expect(one).toHaveBeenCalledOnce(); expect(two.mock.lastCall?.[0].done).toBe(12);
  client.dispose(); client.injectNotification("scan.progress");
  expect(two).toHaveBeenCalledTimes(2);
});

test("set_delay_can_be_changed_and_dispose_clears_delayed_calls", async () => {
  vi.useFakeTimers();
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({}); client.setDelay(100);
  const promise = client.call("inbox.list", {}), assertion = expect(promise).rejects.toMatchObject({ code: "INTERNAL" });
  await waitFor(); client.dispose(); await assertion;
  expect(vi.getTimerCount()).toBe(0);
});

test("mock_settings_configured_returns_configured_email", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ scenario: "settings.configured" });
  expect((await client.call("settings.get", {})).secContactEmail).toBe("name@example.com");
  client.dispose();
});

test("mock_unknown_method_rejects_invalid_argument", async () => {
  const { createMockRpcClient } = await import("./client");
  const client = createMockRpcClient({ scenario: "today.pending" });
  await expect(client.call("unknown.method" as MethodName, {})).rejects.toMatchObject({ code: "INVALID_ARGUMENT" });
  client.dispose();
});
