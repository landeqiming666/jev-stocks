import { expect, test } from "./fixture";
import type { Page } from "@playwright/test";

const ROUTES = [
  { hash: "#/today", heading: /今天有 2 件事需要你看一眼/ },
  { hash: "#/holdings", heading: /持仓/ },
  { hash: "#/scan", heading: /扫描/ },
  { hash: "#/trading", heading: /交易/ },
  { hash: "#/risk", heading: /风险/ },
  { hash: "#/settings", heading: /设置/ },
] as const;

async function noHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

test("six pages show demo data at 1440x900 and 1024x700", async ({ core, app }) => {
  const errors: string[] = [];
  app.on("pageerror", error => errors.push(error.message));
  app.on("console", message => {
    // 浏览器会为缺失的 favicon 报 404，与应用无关。
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) {
      errors.push(message.text());
    }
  });
  await core.result("demo.load");

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 700 },
  ]) {
    await app.setViewportSize(viewport);
    for (const route of ROUTES) {
      await app.goto(`/${route.hash}`);
      await expect(app.getByRole("heading", { name: route.heading }).first()).toBeVisible();
      expect(await noHorizontalScroll(app)).toBe(true);
    }
  }
  expect(errors).toEqual([]);
});

test("today shows the pending cards and evidence drawer", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
  await expect(app.getByText("ZZCL").first()).toBeVisible();
  await expect(app.getByText("系统拿不准的 1 条")).toBeVisible();

  await app.getByRole("button", { name: "查看原文" }).first().click();
  await expect(app.getByRole("dialog")).toBeVisible();
  await expect(app.getByText(/4\.5%/).first()).toBeVisible();
  await expect(app.getByText(/JEVDB/).first()).toBeVisible();
});

test("holdings page lists five holdings and six theses", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/holdings");
  await expect(app.getByRole("heading", { name: "持仓", exact: true })).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
  await expect(app.getByText("天顶弧机器人").first()).toBeVisible();
});

test("trading page advances the demo clock one trading day", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/trading");
  await expect(app.getByRole("heading", { name: "交易", exact: true })).toBeVisible();
  await expect(app.getByText("2026-10-29").first()).toBeVisible();
  await app.getByRole("button", { name: /下一交易日/ }).click();
  await expect(app.getByText("2026-10-30").first()).toBeVisible();
});

test("risk page shows correlation for three holdings", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/risk");
  await expect(app.getByRole("heading", { name: "风险", exact: true })).toBeVisible();
  await expect(app.getByText("年化波动率")).toBeVisible();
  await expect(app.getByRole("img", { name: /相关系数热图，3 只标的/ })).toBeVisible();
});

test("settings page reports demo data loaded", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/settings");
  await expect(app.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await expect(app.getByText("已载入演示数据")).toBeVisible();
});
