import { expect, test, emitStatus } from "../real-core/fixture";
import { DEMO_SCRIPT, DEMO_SECONDS } from "./demo-script";
import type { Page } from "@playwright/test";

const PAGES = [
  { hash: "#/today", heading: /今天有 2 件事/ },
  { hash: "#/holdings", heading: /持仓/ },
  { hash: "#/scan", heading: /扫描/ },
  { hash: "#/trading", heading: /交易/ },
  { hash: "#/risk", heading: /风险/ },
  { hash: "#/settings", heading: /设置/ },
] as const;

async function scrollFits(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

test("M-2 offline keeps six pages readable with demo data", async ({ core, app }) => {
  await core.result("demo.load");
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
  expect(errors).toEqual([]);
});

test("M-3 settings never renders a stored key", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/settings");
  await expect(app.getByText("已载入演示数据")).toBeVisible();
  await expect(app.getByText(/保存后只显示/)).toBeVisible();
  const body = await app.locator("body").innerText();
  expect(body).not.toContain("sk-");
  expect(body).not.toContain("Bearer ");
});

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
