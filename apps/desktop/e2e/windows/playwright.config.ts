import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

const port = 1476;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: ".",
  testMatch: "windows-ui.spec.ts",
  outputDir: "results/playwright",
  workers: 1,
  webServer: {
    cwd: resolve(import.meta.dirname, "../.."),
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    env: { VITE_RPC: "mock" },
    reuseExistingServer: false,
  },
  use: {
    baseURL,
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
    trace: "on",
  },
});
