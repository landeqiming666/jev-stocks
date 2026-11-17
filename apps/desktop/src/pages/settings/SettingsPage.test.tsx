import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useAppStore } from "../../app/store";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import { RpcError, type Bootstrap, type RpcClient, type Settings } from "../../rpc";
import SettingsPage from "./index";

function example(method: keyof typeof MOCK_EXAMPLES, name: string) {
  const entry = MOCK_EXAMPLES[method].find(item => item.name === name);
  if (!entry || !("result" in entry)) throw new Error("fixture missing");
  return structuredClone(entry.result);
}
let stored: Settings, boot: Bootstrap, key: boolean;
type TestCall = (method: string, params: Record<string, unknown>, options?: { signal?: AbortSignal }) => Promise<unknown>;
let call: ReturnType<typeof vi.fn<TestCall>>;
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => {
  stored = example("settings.get", "configured") as unknown as Settings;
  boot = example("app.bootstrap", "ready") as unknown as Bootstrap;
  key = true;
  call = vi.fn(async (method: string, params: Record<string, unknown>) => {
    if (method === "settings.get") return structuredClone(stored);
    if (method === "secrets.status") return { jevKey: key };
    if (method === "settings.update") { stored = { ...stored, ...params }; return structuredClone(stored); }
    if (method === "secrets.set") { key = true; return { ok: true }; }
    if (method === "secrets.clear") { key = false; return { ok: true }; }
    if (method === "settings.testConnection") return example(method, "ok");
    if (method === "demo.load") { stored.demoDataLoaded = true; return example(method, "ok"); }
    if (method === "demo.clear") { stored.demoDataLoaded = false; return { ok: true }; }
    if (method === "app.bootstrap") return { ...boot, configured: { jevKey: key, secEmail: !!stored.secContactEmail },
      demoDataLoaded: stored.demoDataLoaded, engine: { ...boot.engine, requested: stored.engine,
        active: !key || stored.engine === "jevdb" ? null : "jev_direct" } };
    throw new Error("unexpected method");
  });
  useAppStore.setState({ client: { call } as unknown as RpcClient, bootstrap: { status: "ready", value: boot, error: null } });
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); vi.restoreAllMocks(); });
async function open() {
  render(<SettingsPage />);
  await screen.findByRole("heading", { name: "密钥与联系方式" });
}
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

test("settings_configured_hides_key_value", async () => {
  await open();
  expect(screen.getByText("已保存")).toBeTruthy();
  expect(document.body.textContent).not.toContain("test-key-do-not-use");
  expect(screen.queryByLabelText("Jev 密钥")).toBeNull();
});
test("settings_save_key_clears_input", async () => {
  key = false; await open();
  const input = screen.getByLabelText("Jev 密钥") as HTMLInputElement;
  fireEvent.input(input, { target: { value: "test-key-do-not-use" } });
  expect(input.type).toBe("password");
  expect(input.getAttribute("value")).toBeNull();
  fireEvent.click(button("保存密钥"));
  await screen.findByText("已保存");
  expect(input.value).toBe("");
  await waitFor(() => expect(document.activeElement === button("替换")).toBe(true));
  expect(JSON.stringify(useAppStore.getState())).not.toContain("test-key-do-not-use");
  expect(useAppStore.getState().bootstrap.value?.configured.jevKey).toBe(true);
});
test("settings_clear_key_requires_confirm", async () => {
  await open(); button("清除").focus(); fireEvent.click(button("清除"));
  expect(call.mock.calls.some(args => args[0] === "secrets.clear")).toBe(false);
  expect(screen.getByRole("dialog").textContent).toContain("清除后扫描无法开始");
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(document.activeElement).toBe(button("清除"));
  fireEvent.click(button("清除")); fireEvent.click(button("确认清除"));
  await screen.findByLabelText("Jev 密钥");
  await waitFor(() => expect(document.activeElement === screen.getByLabelText("Jev 密钥")).toBe(true));
  expect(useAppStore.getState().bootstrap.value?.configured.jevKey).toBe(false);
});
test("settings_invalid_email_blocks_update", async () => {
  await open(); fireEvent.change(screen.getByLabelText("SEC 联系邮箱"), { target: { value: "abc" } });
  fireEvent.click(button("保存邮箱")); await screen.findByText("联系邮箱格式不正确");
  expect(call.mock.calls.some(args => args[0] === "settings.update")).toBe(false);
});
test("settings_test_connection_renders_three_rows", async () => {
  await open(); fireEvent.click(button("测试连接"));
  const list = await screen.findByRole("list", { name: "连接测试结果" });
  expect(within(list).getAllByRole("listitem").map(row => row.querySelector("strong")?.textContent)).toEqual(["Jev", "SEC", "JEVDB"]);
  expect(list.textContent).toContain("412 ms");
  expect(list.textContent).not.toContain("null ms");
});
test("settings_jevdb_failure_keeps_overall_ok", async () => {
  await open(); fireEvent.click(button("测试连接"));
  await screen.findByText("日常运行可用");
  expect(screen.getByText(/最终验收仍需 JEVDB/)).toBeTruthy();
});
test("explicit_jevdb_unavailable_blocks_scan_and_overall_ok", async () => {
  stored.engine = "jevdb"; boot.engine = { ...boot.engine, requested: "jevdb", active: null };
  await open(); fireEvent.click(button("测试连接"));
  await screen.findByText("连接测试未通过");
  expect(screen.queryByText("日常运行可用")).toBeNull();
  expect(screen.getByText("JEVDB 不可用，将阻止扫描")).toBeTruthy();
});
test("settings_privacy_table_is_read_only", async () => {
  stored.allowedDomains[0]!.domain = "gateway.example.net"; await open();
  const table = screen.getByRole("table", { name: "外联域名" });
  expect(within(table).getAllByRole("row")).toHaveLength(6);
  expect(within(table).queryByRole("textbox")).toBeNull();
  expect(within(table).queryByRole("button")).toBeNull();
  expect(table.textContent).toContain("gateway.example.net");
  expect(table.textContent).not.toContain("api.typesafe.ai");
});
test("settings_demo_conflict_shows_message", async () => {
  stored.demoDataLoaded = false;
  call.mockImplementationOnce(async () => structuredClone(stored));
  const original = call.getMockImplementation()!;
  call.mockImplementation(async (method, params) => {
    if (method === "demo.load") throw new RpcError("CONFLICT", "private backend text");
    return original(method, params);
  });
  await open(); fireEvent.click(button("载入演示数据"));
  await screen.findByText(/演示数据已载入/);
  expect(document.body.textContent).toContain("真实数据");
});
test("running_conflict_preserves_email_and_key_and_does_not_reflect_error_payload", async () => {
  await open(); fireEvent.click(button("替换"));
  fireEvent.input(screen.getByLabelText("Jev 密钥"), { target: { value: "test-key-do-not-use" } });
  fireEvent.change(screen.getByLabelText("SEC 联系邮箱"), { target: { value: "draft@example.com" } });
  const original = call.getMockImplementation()!;
  call.mockImplementation(async (method, params) => {
    if (method === "settings.update" || method === "secrets.clear" || method === "secrets.set")
      throw new RpcError("CONFLICT", "test-key-do-not-use", false, { value: "test-key-do-not-use" });
    return original(method, params);
  });
  fireEvent.click(button("保存邮箱")); await screen.findByText(/扫描正在进行/);
  expect((screen.getByLabelText("SEC 联系邮箱") as HTMLInputElement).value).toBe("draft@example.com");
  fireEvent.click(button("保存密钥")); await waitFor(() => expect(button("保存密钥").disabled).toBe(false));
  expect((screen.getByLabelText("Jev 密钥") as HTMLInputElement).value).toBe("test-key-do-not-use");
  expect(document.body.innerHTML).not.toContain("test-key-do-not-use");
  button("清除").focus(); fireEvent.click(button("清除")); fireEvent.click(button("确认清除"));
  await waitFor(() => expect(button("确认清除").disabled).toBe(false));
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect(useAppStore.getState().bootstrap.value?.configured.jevKey).toBe(true);
});
test("unrelated_save_and_failed_refresh_preserve_unsaved_inputs", async () => {
  await open(); fireEvent.change(screen.getByLabelText("SEC 联系邮箱"), { target: { value: "draft@example.com" } });
  fireEvent.change(screen.getByLabelText("每日 token 上限"), { target: { value: "3000000" } });
  fireEvent.click(screen.getByRole("radio", { name: "Jev 直连" }));
  await waitFor(() => expect(useAppStore.getState().bootstrap.value?.engine.requested).toBe("jev_direct"));
  expect((screen.getByLabelText("SEC 联系邮箱") as HTMLInputElement).value).toBe("draft@example.com");
  expect((screen.getByLabelText("每日 token 上限") as HTMLInputElement).value).toBe("3000000");
  call.mockRejectedValue(new RpcError("INTERNAL", "sensitive"));
  fireEvent.click(button("刷新设置")); await screen.findByText(/暂时无法完成/);
  expect((screen.getByLabelText("SEC 联系邮箱") as HTMLInputElement).value).toBe("draft@example.com");
});
test("demo_async_buttons_confirmation_and_shared_bootstrap", async () => {
  stored.demoDataLoaded = false; await open();
  const pending = deferred<unknown>(), original = call.getMockImplementation()!;
  call.mockImplementation(async (method, params) => {
    if (method === "demo.load") { await pending.promise; stored.demoDataLoaded = true; return example(method, "ok"); }
    return original(method, params);
  });
  fireEvent.click(button("载入演示数据")); expect(button("载入演示数据").disabled).toBe(true);
  await act(async () => pending.resolve(undefined));
  await waitFor(() => expect(useAppStore.getState().bootstrap.value?.demoDataLoaded).toBe(true));
  fireEvent.click(button("清除演示数据"));
  expect(call.mock.calls.some(args => args[0] === "demo.clear")).toBe(false);
  fireEvent.click(button("确认清除"));
  await waitFor(() => expect(useAppStore.getState().bootstrap.value?.demoDataLoaded).toBe(false));
});
test("stale_read_cannot_replace_new_client_or_shared_bootstrap", async () => {
  const pending = deferred<Settings>(); call.mockImplementationOnce(() => pending.promise);
  render(<SettingsPage />);
  const next = { call: vi.fn(async (method: string) => method === "settings.get" ? { ...stored, secContactEmail: "next@example.com" } : method === "app.bootstrap" ? boot : { jevKey: false }) } as unknown as RpcClient;
  act(() => useAppStore.setState({ client: next }));
  await screen.findByDisplayValue("next@example.com");
  await act(async () => pending.resolve(stored));
  expect((screen.getByLabelText("SEC 联系邮箱") as HTMLInputElement).value).toBe("next@example.com");
});
test("stale_connection_result_is_discarded_after_configuration_change", async () => {
  await open(); const pending = deferred<unknown>(), original = call.getMockImplementation()!;
  call.mockImplementation((method, params) => method === "settings.testConnection" ? pending.promise : original(method, params));
  fireEvent.click(button("测试连接"));
  fireEvent.click(screen.getByRole("radio", { name: "Jev 直连" }));
  await waitFor(() => expect(useAppStore.getState().bootstrap.value?.engine.requested).toBe("jev_direct"));
  await act(async () => pending.resolve(example("settings.testConnection", "ok")));
  expect(screen.queryByRole("list", { name: "连接测试结果" })).toBeNull();
});
test("unmount_aborts_reads_and_cannot_publish_write_bootstrap", async () => {
  await open(); const pending = deferred<unknown>();
  const signal = call.mock.calls[0]![2]!.signal!;
  call.mockClear();
  call.mockImplementation(method => method === "secrets.clear" ? pending.promise : Promise.resolve(boot));
  fireEvent.click(button("清除")); fireEvent.click(button("确认清除"));
  cleanup(); await act(async () => pending.resolve({ ok: true }));
  expect(call.mock.calls.filter(args => args[0] === "app.bootstrap")).toHaveLength(0);
  expect(signal.aborted).toBe(true);
});
test("successful_secret_write_clears_local_input_even_if_bootstrap_refresh_fails", async () => {
  key = false; await open();
  const original = call.getMockImplementation()!;
  call.mockImplementation(async (method, params) => {
    if (method === "app.bootstrap") throw new RpcError("INTERNAL", "test-key-do-not-use");
    return original(method, params);
  });
  const input = screen.getByLabelText("Jev 密钥") as HTMLInputElement;
  fireEvent.input(input, { target: { value: "test-key-do-not-use" } });
  fireEvent.click(button("保存密钥"));
  await screen.findByText(/共享状态刷新失败/);
  expect(input.value).toBe("");
  expect(document.body.innerHTML).not.toContain("test-key-do-not-use");
  expect(screen.getByText("已保存")).toBeTruthy();
});
test("typing_during_email_save_preserves_newer_local_draft", async () => {
  await open(); const pending = deferred<unknown>(), original = call.getMockImplementation()!;
  call.mockImplementation(async (method, params) => {
    if (method === "settings.update") await pending.promise;
    return original(method, params);
  });
  const input = screen.getByLabelText("SEC 联系邮箱") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "submitted@example.com" } });
  fireEvent.click(button("保存邮箱"));
  fireEvent.change(input, { target: { value: "newer@example.com" } });
  await act(async () => pending.resolve(undefined));
  await waitFor(() => expect(button("保存邮箱").disabled).toBe(false));
  expect(input.value).toBe("newer@example.com");
  expect(stored.secContactEmail).toBe("submitted@example.com");
});
test("stale_write_bootstrap_cannot_publish_into_new_client", async () => {
  await open(); const pending = deferred<unknown>(), original = call.getMockImplementation()!;
  call.mockImplementation((method, params) => method === "app.bootstrap" ? pending.promise : original(method, params));
  fireEvent.click(screen.getByRole("radio", { name: "Jev 直连" }));
  await waitFor(() => expect(call.mock.calls.filter(args => args[0] === "app.bootstrap")).toHaveLength(2));
  const nextBoot = { ...boot, appVersion: "next-session" };
  const next = { call: vi.fn(async (method: string) => method === "settings.get" ? stored : method === "app.bootstrap" ? nextBoot : { jevKey: true }) } as unknown as RpcClient;
  act(() => useAppStore.setState({ client: next }));
  await screen.findByText("next-session");
  await act(async () => pending.resolve(boot));
  expect(useAppStore.getState().bootstrap.value?.appVersion).toBe("next-session");
});
test("refresh_invalidates_connection_from_previous_configuration", async () => {
  await open(); fireEvent.click(button("测试连接")); await screen.findByText("日常运行可用");
  key = false; fireEvent.click(button("刷新设置"));
  await screen.findByLabelText("Jev 密钥");
  expect(screen.queryByText("日常运行可用")).toBeNull();
  expect(useAppStore.getState().bootstrap.value?.engine.active).toBeNull();
});
test("real_unconfigured_bootstrap_keeps_all_sections_despite_replay_and_focus_hash", async () => {
  key = false; stored.secContactEmail = null;
  window.history.replaceState(null, "", "#/settings?state=test-ok&focusModal=test-key-do-not-use");
  await open();
  expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(6);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.queryByText("日常运行可用")).toBeNull();
  expect(document.body.innerHTML).not.toContain("test-key-do-not-use");
  expect(useAppStore.getState().bootstrap.value?.engine.active).toBeNull();
});
