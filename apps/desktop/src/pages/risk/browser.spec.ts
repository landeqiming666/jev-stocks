import { test, expect, type Page } from "@playwright/test";
import { resolve } from "node:path";
import { feedback } from "../../i18n/zh-CN/feedback";

const gallery = "/src/pages/risk/dev-gallery.html";
const screenshots = resolve(process.cwd(), "../../docs/wp/status");
async function ready(page: Page, state = "ok", extra = "") {
  await page.goto(`${gallery}?fixture=${state}${extra}#/risk`);
  await expect(page.locator('.p-risk[data-ready="true"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator("main").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
}
for (const viewport of [{ width: 1280, height: 820 }, { width: 1024, height: 700 }]) {
  for (const state of ["ok", "ok-table", "insufficient", "singular", "unadjusted"]) {
    test(`${viewport.width} ${state} browser and screenshot`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.setViewportSize(viewport);
      await ready(page, state === "ok-table" ? "ok" : state);
      if (state === "ok-table") await page.getByRole("button", { name: "表格视图" }).click();
      if (state === "insufficient") {
        await expect(page.getByText(/至少需要 60 天/)).toBeVisible();
        await expect(page.locator(".c-metric")).toHaveCount(0);
      } else {
        await expect(page.locator(".c-metric")).toHaveCount(4);
        await expect(page.locator(".c-barlist__row")).toHaveCount(5);
      }
      if (state === "singular") await expect(page.getByText("协方差矩阵接近奇异")).toBeVisible();
      if (state === "unadjusted") {
        await expect(page.getByText("价格未复权", { exact: true }).first()).toBeVisible();
        await expect(page.getByText(/价格已复权/)).toHaveCount(0);
      }
      await noOverflow(page);
      await page.screenshot({ path: resolve(screenshots, `U-06-${viewport.width}-${state}.png`) });
      expect(errors).toEqual([]);
    });
  }
}
test("keyboard tab windows heatmap tooltip and Space/Enter table toggle", async ({ page }) => {
  await ready(page);
  await page.getByRole("radio", { name: "1Y" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "3Y" })).toBeFocused();
  await expect(page.getByText(/实际窗口 3Y/)).toBeVisible();
  await expect(page.getByRole("radio", { name: "人民币" })).toBeDisabled();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("radio", { name: "美元" })).toBeFocused();
  await page.keyboard.press("Tab");
  const toggle = page.getByRole("button", { name: "表格视图" });
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Tab");
  const first = page.locator('[data-row="0"][data-col="0"]');
  await expect(first).toBeFocused();
  await expect(page.getByRole("tooltip")).toContainText("ρ = 1.00");
  await page.keyboard.press("ArrowRight");
  await expect(page.locator('[data-row="0"][data-col="1"]')).toBeFocused();
  await expect(page.getByRole("tooltip")).toContainText("ZZAR 与 ZZFD：ρ = 0.21");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await toggle.focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("table", { name: /相关系数/ })).toBeVisible();
  await expect(page.locator(".c-heatmap")).toHaveCount(0);
  await page.keyboard.press("Enter");
  await expect(page.locator(".c-heatmap")).toBeVisible();
  await page.locator('[data-row="0"][data-col="1"]').hover();
  await expect(page.getByRole("tooltip")).toContainText("ρ = 0.21");
});
test("old RPC replies are cancelled and cannot replace latest window", async ({ page }) => {
  await ready(page);
  await page.evaluate(() => { window.riskDev.delays = { "6M": 1000, "1Y": 30 }; });
  await page.getByRole("radio", { name: "6M" }).click();
  await expect(page.getByText(/当前显示上次 1Y/)).toBeVisible();
  await page.getByRole("radio", { name: "1Y" }).click();
  await expect(page.locator('.p-risk[data-ready="true"]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.riskDev.lateReplies.length)).toBeGreaterThan(0);
  await expect(page.getByText(/实际窗口 1Y/)).toBeVisible();
  const params = await page.evaluate(() => window.riskDev.calls.filter(call => call.method === "risk.compute").map(call => call.params));
  expect(params.every(value => value.scope === "holdings" && value.currency === "USD")).toBe(true);
  expect(params.at(-1)?.window).toBe("1Y");
});
test("refresh prices is serial; failure retains cache and retry succeeds", async ({ page }) => {
  await ready(page);
  await page.evaluate(() => { window.riskDev.delays["prices.refresh"] = 300; });
  await page.getByRole("button", { name: "刷新行情" }).click();
  await expect(page.getByRole("button", { name: "重新计算" })).toBeDisabled();
  await page.getByRole("radio", { name: "3Y" }).click();
  await expect(page.locator('.p-risk[data-ready="true"]')).toBeVisible();
  const calls = await page.evaluate(() => window.riskDev.calls.filter(call => call.method !== "app.bootstrap"));
  expect(calls.map(call => call.method)).toEqual(["risk.compute", "prices.refresh", "risk.compute"]);
  expect(calls.at(-1)?.params.window).toBe("3Y");
  await page.evaluate(() => { window.riskDev.failPrices = true; });
  await page.getByRole("button", { name: "刷新行情" }).click();
  await expect(page.getByText(/数据未更新；/)).toBeVisible();
  await expect(page.getByText("18.7%", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "重新计算" }).click();
  await expect(page.getByText(/数据未更新；/)).toHaveCount(0);
});
test("null and zero variance cells have full numeric table alternative", async ({ page }) => {
  await ready(page, "null");
  await expect(page.locator(".c-heatmap__cell.is-na")).toHaveCount(9);
  await page.getByRole("button", { name: "表格视图" }).click();
  await expect(page.getByRole("table").locator("td", { hasText: "—" })).toHaveCount(9);
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(6);
  await ready(page, "zero");
  await expect(page.locator(".c-heatmap__cell.is-na")).toHaveCount(25);
  await expect(page.getByText("4.67", { exact: true })).toBeVisible();
  await expect(page.locator(".c-barlist__row")).toHaveCount(0);
});
test("offline feedback host has one banner and local risk remains available", async ({ page }) => {
  await ready(page, "ok", "&offline=1");
  await expect(page.getByText("18.7%", { exact: true })).toBeVisible();
  await expect(page.getByText(feedback.offline, { exact: true })).toHaveCount(1);
  await expect(page.locator(".p-risk .c-banner")).toHaveCount(0);
});
test("single asset hides charts but preserves metrics", async ({ page }) => {
  await ready(page, "single");
  await expect(page.getByText(/至少需要 2 只持仓才能显示相关性/)).toBeVisible();
  await expect(page.getByText(/主成分分析至少需要 2 只标的/)).toBeVisible();
  await expect(page.locator(".c-metric")).toHaveCount(4);
  await expect(page.locator(".c-heatmap")).toHaveCount(0);
});
test("unmount aborts pending request and late completion has no page errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await ready(page);
  await page.evaluate(() => { window.riskDev.delays["6M"] = 300; });
  await page.getByRole("radio", { name: "6M" }).click();
  await page.evaluate(() => { location.hash = "#/settings"; });
  await expect.poll(() => page.evaluate(() => window.riskDev.lateReplies.length)).toBeGreaterThan(0);
  await expect(page.locator(".p-risk")).toHaveCount(0);
  expect(errors).toEqual([]);
});
