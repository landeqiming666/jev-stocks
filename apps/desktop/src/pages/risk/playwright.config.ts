import { defineConfig } from "@playwright/test";
import { env } from "node:process";

export default defineConfig({
  testDir: ".",
  testMatch: "browser.spec.ts",
  outputDir: "./.browser-output",
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:1466",
    viewport: { width: 1280, height: 820 },
    reducedMotion: "reduce",
    timezoneId: "Asia/Shanghai",
    browserName: "chromium",
    headless: true,
    launchOptions: { executablePath: env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
  },
});
