import { defineConfig } from "@playwright/test";
import { chromiumExecutable } from "./e2e/browser";

export default defineConfig({
  testDir: "./e2e/real-core",
  testMatch: ["*.spec.ts"],
  globalSetup: "./e2e/real-core/global-setup.ts",
  outputDir: "../../test-results/e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
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
    cwd: ".",
    url: "http://127.0.0.1:1469",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
