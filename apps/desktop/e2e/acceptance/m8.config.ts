import { defineConfig } from "@playwright/test";
import { chromiumExecutable } from "../browser";

export default defineConfig({
  testDir: ".",
  testMatch: ["m8.spec.ts"],
  outputDir: `../../../test-results/m8-${Date.now()}`,
  workers: 1,
  retries: 0,
  timeout: 480_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:1471",
    viewport: { width: 1440, height: 900 },
    headless: true,
    reducedMotion: "reduce",
    trace: "off",
    launchOptions: { executablePath: chromiumExecutable() },
  },
  webServer: {
    command: "pnpm exec vite --host 127.0.0.1 --port 1471 --strictPort",
    cwd: "../..",
    env: { VITE_RPC: "tauri" },
    url: "http://127.0.0.1:1471",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
