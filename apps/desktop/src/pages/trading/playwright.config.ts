import { defineConfig } from "@playwright/test";
import { env } from "node:process";

export default defineConfig({
  testDir: ".", testMatch: "browser.spec.ts", outputDir: "../../../test-results/u05-browser-output",
  workers: 1, timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:1465", viewport: { width: 1280, height: 820 }, reducedMotion: "reduce",
    browserName: "chromium", headless: true, trace: "retain-on-failure",
    launchOptions: { executablePath: env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
  },
});
