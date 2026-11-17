import { defineConfig } from "@playwright/test";
import { env } from "node:process";

export default defineConfig({
  testDir: ".", testMatch: "browser.spec.ts", workers: 1, timeout: 30_000,
  outputDir: "../../../test-results/u04-browser-output",
  use: { baseURL: "http://127.0.0.1:1464", browserName: "chromium", headless: true,
    reducedMotion: "reduce", timezoneId: "Asia/Shanghai",
    launchOptions: { executablePath: env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } },
});
