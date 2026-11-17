import { defineConfig } from "@playwright/test";
import { join, resolve } from "node:path";
import { chromiumExecutable } from "../browser";

const artifacts = process.env.SENTINEL_ACCEPTANCE_ARTIFACTS ?? resolve(`test-results/acceptance-${Date.now()}`);

// M-3 会真实调用 secrets.set；验收核心必须使用进程内存存储，绝不读写用户钥匙串。
process.env.SENTINEL_ACCEPTANCE_MEMORY_SECRETS = "1";
// 用例写出的 M-3 证据必须与报告读取的目录一致。
process.env.SENTINEL_ACCEPTANCE_ARTIFACTS = artifacts;

export default defineConfig({
  testDir: ".",
  testMatch: ["acceptance.spec.ts"],
  outputDir: join(artifacts, "traces"),
  workers: 1,
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["json", { outputFile: join(artifacts, "results.json") }], ["list"]],
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
