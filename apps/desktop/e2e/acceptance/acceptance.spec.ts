import { expect, test, emitStatus } from "../real-core/fixture";
import { DEMO_SCRIPT, DEMO_SECONDS } from "./demo-script";
import type { Page } from "@playwright/test";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PAGES = [
  { hash: "#/today", heading: /今天有 2 件事/ },
  { hash: "#/holdings", heading: /持仓/ },
  { hash: "#/scan", heading: /扫描/ },
  { hash: "#/trading", heading: /交易/ },
  { hash: "#/risk", heading: /风险/ },
  { hash: "#/settings", heading: /设置/ },
] as const;

const EXPECTED_COUNTS = {
  instruments: 6,
  holdings: 5,
  theses: 6,
  events: 6,
  decisions: 12,
  prices: 1560,
};
const SENTINEL = "test-key-do-not-use";
const SYNTHETIC_EMAIL = "acceptance@example.com";

type Json = Record<string, unknown>;

async function scrollFits(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

function filesUnder(directory: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(directory);
  } catch {
    return [];
  }
  const files: string[] = [];
  for (const entry of entries) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) files.push(...filesUnder(path));
    else files.push(path);
  }
  return files;
}

function writeEvidence(name: string, payload: unknown): void {
  const directory = process.env.SENTINEL_ACCEPTANCE_ARTIFACTS;
  if (!directory) throw new Error("SENTINEL_ACCEPTANCE_ARTIFACTS is required for evidence");
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, name), JSON.stringify(payload, null, 2) + "\n", "utf8");
}

function errorCode(message: Json): unknown {
  return (message.error as Json | undefined)?.code;
}

function errorReason(message: Json): unknown {
  const error = message.error as Json | undefined;
  return (error?.data as Json | undefined)?.reason;
}

function errorMissing(message: Json): unknown {
  const error = message.error as Json | undefined;
  return (error?.data as Json | undefined)?.missing;
}

test("M-1 demo data clears and reloads to fixed counts", async ({ core, app }) => {
  const first = (await core.result("demo.load")).counts;
  expect(first).toEqual(EXPECTED_COUNTS);
  const cleared = await core.result("demo.clear");
  expect(cleared.ok).toBe(true);
  const reloaded = (await core.result("demo.load")).counts;
  expect(reloaded).toEqual(EXPECTED_COUNTS);

  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
});

test("M-2 offline keeps six pages readable and blocks scanning", async ({ core, app }) => {
  await core.result("demo.load");
  await core.result("settings.update", { secContactEmail: SYNTHETIC_EMAIL });
  await core.result("secrets.set", { name: "jevKey", value: SENTINEL });

  const blocked = await core.request("scan.start", { market: "us" });
  expect(errorCode(blocked)).toBe("SOURCE_UNAVAILABLE");
  expect(errorReason(blocked)).toBe("OFFLINE");

  const errors: string[] = [];
  app.on("pageerror", error => errors.push(error.message));
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 700 },
  ]) {
    await app.setViewportSize(viewport);
    for (const route of PAGES) {
      await app.goto(`/${route.hash}`);
      await expect(app.getByRole("heading", { name: route.heading }).first()).toBeVisible();
      expect(await scrollFits(app)).toBe(true);
    }
  }
  await app.goto("/#/today");
  await expect(app.getByText("当前离线，显示的是上次的结果。").first()).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
  const scanButton = app.getByRole("button", { name: "立即扫描" });
  await expect(scanButton).toBeDisabled();
  await expect(scanButton).toHaveAttribute("title", "当前离线，无法开始扫描。");
  expect(errors).toEqual([]);
});

test("M-2 keyboard navigation and scan drawer restore focus", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();

  const holdings = app.getByRole("link", { name: "持仓" });
  await holdings.focus();
  await app.keyboard.press("Enter");
  await expect(app).toHaveURL(/#\/holdings$/);
  await expect(app.getByRole("heading", { name: /持仓/ }).first()).toBeVisible();
  expect(await app.evaluate(() => document.activeElement?.tagName)).toBe("H1");

  await app.goto("/#/scan");
  await expect(app.getByRole("heading", { name: "扫描" }).first()).toBeVisible();
  const row = app.locator("tbody tr[data-run-id]").first();
  await expect(row).toBeVisible();
  await row.focus();
  await app.keyboard.press("Enter");
  const drawer = app.getByRole("dialog");
  await expect(drawer).toBeVisible();
  expect(
    await app.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null),
  ).toBe(true);
  await app.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  expect(await row.evaluate(element => element === document.activeElement)).toBe(true);
});

test("M-3 secrets never leak through UI, RPC, or core logs", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/settings");
  await expect(app.getByRole("heading", { name: "设置" })).toBeVisible();

  await app.getByLabel("Jev 密钥").fill(SENTINEL);
  await app.getByRole("button", { name: "保存密钥" }).click();
  await expect(app.getByText("已保存", { exact: true })).toBeVisible();
  await expect(app.locator('input[type="password"]')).toHaveCount(0);

  await app.getByLabel("SEC 联系邮箱").fill(SYNTHETIC_EMAIL);
  await app.getByRole("button", { name: "保存邮箱" }).click();
  await expect(app.getByLabel("SEC 联系邮箱")).toHaveValue(SYNTHETIC_EMAIL);

  const statusBefore = await core.result("secrets.status");
  const settings = JSON.stringify(await core.result("settings.get"));
  const bootstrap = JSON.stringify(await core.result("app.bootstrap"));
  const connection = JSON.stringify(await core.result("settings.testConnection"));
  const configuredScan = await core.request("scan.start", { market: "us" });
  const body = await app.locator("body").innerText();

  expect(statusBefore.jevKey).toBe(true);
  expect(settings).not.toContain(SENTINEL);
  expect(bootstrap).not.toContain(SENTINEL);
  expect(connection).not.toContain(SENTINEL);
  expect(body).not.toContain(SENTINEL);
  expect(errorCode(configuredScan)).toBe("SOURCE_UNAVAILABLE");
  expect(errorReason(configuredScan)).toBe("OFFLINE");

  const logFiles = filesUnder(join(core.dataDir, "logs"));
  expect(logFiles.length).toBeGreaterThan(0);
  for (const path of logFiles) {
    expect(readFileSync(path, "utf8")).not.toContain(SENTINEL);
  }

  await app.getByRole("button", { name: "清除", exact: true }).click();
  await expect(app.getByRole("heading", { name: "清除 Jev 密钥" })).toBeVisible();
  await app.getByRole("button", { name: "确认清除" }).click();
  await expect(app.getByText("尚未保存 Jev 密钥。")).toBeVisible();

  const statusAfter = await core.result("secrets.status");
  const clearedScan = await core.request("scan.start", { market: "us" });
  expect(statusAfter.jevKey).toBe(false);
  expect(errorCode(clearedScan)).toBe("CONFIG_REQUIRED");
  expect(errorMissing(clearedScan)).toContain("jevKey");

  writeEvidence("m3-credentials.json", {
    memorySecretStore: process.env.SENTINEL_ACCEPTANCE_MEMORY_SECRETS === "1",
    secretVisibleInUi: body.includes(SENTINEL),
    settingsGetClean: !settings.includes(SENTINEL),
    bootstrapClean: !bootstrap.includes(SENTINEL),
    connectionTestClean: !connection.includes(SENTINEL),
    coreLogsClean: logFiles.every(path => !readFileSync(path, "utf8").includes(SENTINEL)),
    coreLogFiles: logFiles.length,
    secretStatusBefore: statusBefore.jevKey,
    secretStatusAfter: statusAfter.jevKey,
    scanWhileConfiguredError: errorCode(configuredScan),
    scanAfterClearError: errorCode(clearedScan),
    rpcResponses: {
      statusBefore,
      statusAfter,
      configuredScanError: errorSummary(configuredScan),
      clearedScanError: errorSummary(clearedScan),
    },
  });
});

function errorSummary(message: Json): Json {
  const error = message.error as Json | undefined;
  return { code: error?.code ?? null, data: error?.data ?? null };
}

test("M-2 restart keeps cached results visible", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
  await emitStatus(app, "restarting");
  await expect(app.getByText("核心进程正在重启…")).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
});

test("M-2 demo script fits in five minutes", async () => {
  expect(DEMO_SCRIPT.length).toBeGreaterThanOrEqual(8);
  expect(DEMO_SECONDS).toBeLessThanOrEqual(300);
  expect(DEMO_SCRIPT.every(step => step.expected.length > 0 && step.fallback.length > 0)).toBe(true);
});
