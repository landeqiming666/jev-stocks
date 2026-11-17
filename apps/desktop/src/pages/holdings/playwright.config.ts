import { defineConfig } from "@playwright/test";
import { env } from "node:process";
export default defineConfig({
  testDir: ".", testMatch: "browser.spec.ts", outputDir: "../../../test-results/u03/browser-output", workers: 1,
  timeout: 30000, use: { baseURL: "http://127.0.0.1:1463", headless: true, trace: "on", reducedMotion: "reduce",
    launchOptions: { executablePath: env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } },
});
