import { defineConfig } from "@playwright/test";
import { chromiumExecutable } from "../browser";
import { join, resolve } from "node:path";

const output = process.env.SENTINEL_WINDOWS_REAL_CORE_OUTPUT
  ?? resolve(import.meta.dirname, `../../../test-results/real-core-${Date.now()}`);

export default defineConfig({
  testDir: ".",
  testMatch: ["demo-flow.spec.ts", "failures.spec.ts"],
  globalSetup: "./global-setup.ts",
  outputDir: join(output, "traces"),
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: join(output, "results.json") }]],
  use: {
    baseURL: "http://127.0.0.1:1469",
    viewport: { width: 1440, height: 900 },
    headless: true,
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    launchOptions: { executablePath: chromiumExecutable() },
  },
  webServer: {
    command: "pnpm exec vite --host 127.0.0.1 --port 1469 --strictPort",
    cwd: "../..",
    url: "http://127.0.0.1:1469",
    reuseExistingServer: false,
    env: { VITE_RPC: "tauri" },
    timeout: 60_000,
  },
});
