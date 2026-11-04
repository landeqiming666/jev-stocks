import { defineConfig } from "@playwright/test";
import { chromiumExecutable } from "../browser";

export default defineConfig({
  testDir: ".",
  testMatch: ["acceptance.spec.ts"],
  outputDir: `../../../test-results/acceptance-${Date.now()}`,
  workers: 1,
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["json", { outputFile: "../../../test-results/acceptance/results.json" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:1470",
    viewport: { width: 1440, height: 900 },
    headless: true,
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    launchOptions: { executablePath: chromiumExecutable() },
  },
  webServer: {
    command: "pnpm exec vite --host 127.0.0.1 --port 1470 --strictPort",
    cwd: "../..",
    url: "http://127.0.0.1:1470",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
