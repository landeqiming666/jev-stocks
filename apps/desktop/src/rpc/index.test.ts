import { afterEach, expect, test, vi } from "vitest";
import { getRpcClient } from "./index";

afterEach(() => { vi.unstubAllEnvs(); });

test("mock_environment_selects_mock_client", async () => {
  vi.stubEnv("VITE_RPC", "mock");
  const client = getRpcClient();
  await client.whenReady();
  expect((await client.call("inbox.list", {})).summary.pendingCount).toBe(3);
  expect("injectNotification" in client).toBe(true);
  client.dispose();
});

test("unset_environment_selects_tauri_client", () => {
  vi.stubEnv("VITE_RPC", undefined);
  const client = getRpcClient();
  expect("injectNotification" in client).toBe(false);
  client.dispose();
});
