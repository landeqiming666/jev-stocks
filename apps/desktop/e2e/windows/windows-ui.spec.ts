import { expect, test, type Page } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { common } from "../../src/i18n/zh-CN/common";
import { feedback } from "../../src/i18n/zh-CN/feedback";

const shellRoutes = ["today", "holdings", "trading", "risk", "scan", "settings"] as const;
const mainNavigation = (page: Page) =>
  page.getByRole("navigation", { name: common.mainNavigation, exact: true });

test.beforeEach(async ({ page }) => {
  // Supply the same Windows platform marker that Tauri's init script supplies.
  await page.addInitScript(() => {
    const markWindows = () => { document.documentElement.dataset.platform = "windows"; };
    if (document.documentElement) markWindows();
    document.addEventListener("DOMContentLoaded", markWindows, { once: true });
  });
});

for (const [width, height] of [[1440, 900], [1024, 700]] as const) {
  test(`six shell routes fit ${width}×${height}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    await page.goto("/#/today");
    const nav = mainNavigation(page);
    const main = page.getByRole("main");
    await expect(nav.getByRole("link")).toHaveCount(shellRoutes.length);
    await expect(main.getByRole("heading", { level: 1, name: common.nav.today })).toBeVisible();

    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-platform", "windows");
    const tokens = await html.evaluate(element => {
      const style = window.getComputedStyle(element);
      return {
        inset: style.getPropertyValue("--titlebar-inset-left").trim(),
        font: style.getPropertyValue("--font-cjk").trim(),
        modifier: style.getPropertyValue("--kbd-mod").trim(),
      };
    });
    expect(tokens).toEqual({ inset: "0px", font: '"Microsoft YaHei UI"', modifier: '"Ctrl"' });

    const observed = [];
    for (const route of shellRoutes) {
      const label = common.nav[route];
      const link = nav.getByRole("link", { name: label, exact: true });
      await link.click();
      await expect(link).toHaveAttribute("aria-current", "page");
      expect(new URL(page.url()).hash).toBe(`#/${route}`);
      await expect(main.getByRole("heading", { level: 1, name: label, exact: true })).toBeVisible();
      await expect(page).toHaveTitle(`${label} · ${common.appName}`);
      const layout = await main.evaluate(element => ({
        viewportWidth: window.innerWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        mainWidth: element.clientWidth,
        mainScrollWidth: element.scrollWidth,
      }));
      expect(layout.viewportWidth).toBe(width);
      expect(layout.documentScrollWidth, route).toBeLessThanOrEqual(width);
      expect(layout.mainScrollWidth, route).toBeLessThanOrEqual(layout.mainWidth);
      observed.push({
        route, ...layout,
        placeholderVisible: await main.getByText(common.shellOnly, { exact: true }).isVisible(),
      });
      await page.screenshot({
        path: testInfo.outputPath(`${route}-${width}.png`),
        animations: "disabled",
      });
    }
    const summary = testInfo.outputPath("shell-routes.json");
    await writeFile(summary, JSON.stringify({ width, height, tokens, observed }, null, 2), "utf8");
    await testInfo.attach("shell-routes", { path: summary, contentType: "application/json" });
  });
}

test("browser offline banner leaves shell navigation usable", async ({ page, context }) => {
  await page.goto("/#/today");
  await expect(page.getByRole("heading", { level: 1, name: common.nav.today })).toBeVisible();
  const banner = page.getByText(feedback.offline, { exact: true });
  await expect(banner).toHaveCount(0);
  await context.setOffline(true);
  try {
    await expect(banner).toBeVisible();
    await expect(banner).toHaveCount(1);
    await mainNavigation(page).getByRole("link", { name: common.nav.settings, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: common.nav.settings })).toBeVisible();
  } finally {
    await context.setOffline(false);
  }
  await expect(banner).toHaveCount(0);
  await expect(page.getByText(feedback.online, { exact: true })).toBeVisible();
});

test("U-08 render-error fixture keeps shell navigation usable", async ({ page }) => {
  await page.goto("/src/components/feedback/dev-shell.html#/today");
  await page.getByRole("button", { name: feedback.gallery.crash, exact: true }).click();
  await expect(page.getByText(/错误编号：[A-F0-9]{12}/)).toBeVisible();
  const settings = mainNavigation(page).getByRole("link", {
    name: common.nav.settings, exact: true,
  });
  await settings.click();
  await expect(settings).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(feedback.renderError, { exact: true })).toBeVisible();
});
