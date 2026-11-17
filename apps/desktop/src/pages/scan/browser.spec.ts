import { test, expect, type Page } from "@playwright/test";
import { resolve } from "node:path";

const fixture = "/src/pages/scan/dev-browser.html";
const evidence = resolve("../../docs/wp/status/U-04-screenshots");
async function open(page: Page, state = "default", layers = false) {
  await page.goto(`${fixture}${layers ? "?layers=1" : ""}#/scan?state=${state}`);
  await expect(page.locator('.p-scan[data-ready="true"]')).toBeVisible();
}
async function capture(page: Page, name: string, width: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `${width}-${name}.png`), animations: "disabled" });
}

for (const [width, height] of [[1280, 820], [1024, 700]]) {
  test(`${width}_default_detail_budget_success_partial_retry_cancel_keyboard`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width: width!, height: height! });
    await open(page);
    await expect(page.getByRole("row")).toHaveCount(5);
    await expect(page.getByText("18,420 / 2,000,000 tokens")).toBeVisible();
    await expect(page.locator(".p-scan__budget")).toContainText("估算 —");
    await capture(page, "default", width!);
    const row = page.locator("tr[data-run-id]").nth(1);
    await row.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "扫描明细" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("heading", { name: "扫描明细" })).toBeFocused();
    await expect(row).toHaveAttribute("aria-expanded", "true");
    await expect(dialog).toHaveAttribute("aria-modal", width! < 1200 ? "true" : "false");
    const drawerBox = width! < 1200 ? await dialog.boundingBox() : await page.locator(".l-drawer").boundingBox();
    expect(Math.round(drawerBox!.width)).toBe(400);
    if (width! >= 1200) {
      const main = await page.locator("main").boundingBox();
      expect(Math.round(main!.x + main!.width)).toBe(Math.round(drawerBox!.x));
    }
    expect(await page.locator(".l-content.has-drawer").count()).toBe(width! < 1200 ? 0 : 1);
    await expect(dialog.getByText(/Jev 返回 529.*已重试 3 次/)).toBeVisible();
    await capture(page, "partial", width!);
    await dialog.locator("[data-batch-id]").nth(2).scrollIntoViewIfNeeded();
    await capture(page, "detail", width!);
    if (width! < 1200) {
      await page.getByRole("button", { name: "重试", exact: true }).focus();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "关闭扫描明细" })).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      await expect(page.getByRole("button", { name: "重试", exact: true })).toBeFocused();
    }
    await page.evaluate(() => window.__scanBrowser.retryFailure(true));
    await page.getByRole("button", { name: "重试", exact: true }).click();
    await expect(dialog.getByText(/synthetic browser retry: Jev 529/)).toBeVisible();
    await expect(dialog.getByText("失败", { exact: true })).toBeVisible();
    await capture(page, "retry-error", width!);
    await page.evaluate(() => window.__scanBrowser.retryFailure(false));
    await page.getByRole("button", { name: "重试", exact: true }).focus();
    await page.keyboard.press("Space");
    await expect(page.getByText("已重试成功")).toBeVisible();
    await expect(dialog.locator("[data-batch-id]").nth(2)).toContainText("成功");
    await capture(page, "retry", width!);
    expect(await page.evaluate(() => window.__scanBrowser.calls.filter(call => call.method === "scan.retryBatch").length)).toBe(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0); await expect(row).toBeFocused();
    await page.keyboard.press("Space"); await expect(dialog).toBeVisible();
    await page.getByRole("button", { name: "关闭扫描明细" }).click(); await expect(row).toBeFocused();
    await capture(page, "keyboard", width!);
    await page.locator("tr[data-run-id]").first().click();
    await expect(dialog.getByText("成功", { exact: true })).toBeVisible();
    await capture(page, "success", width!);
    await open(page, "budget");
    await expect(page.getByRole("button", { name: "立即扫描", exact: true })).toBeDisabled();
    await expect(page.locator(".p-scan__budget.is-danger")).toBeVisible();
    await capture(page, "budget", width!);
    await open(page);
    await page.getByRole("button", { name: "立即扫描", exact: true }).click();
    await expect(page.getByText("进行中", { exact: true })).toBeVisible();
    await page.evaluate(() => window.__scanBrowser.progress(9, 17));
    await expect(page.getByText("9 / 17")).toBeVisible();
    await expect(page.getByRole("button", { name: "立即扫描", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "取消扫描", exact: true }).click();
    await expect(page.getByRole("button", { name: "取消扫描", exact: true })).toBeDisabled();
    await expect(page.getByText("进行中", { exact: true })).toBeVisible();
    await page.evaluate(() => window.__scanBrowser.finish("cancelled"));
    await expect(page.getByRole("button", { name: "取消扫描", exact: true })).toHaveCount(0);
    await expect(page.locator("tr[data-run-id]").first()).toContainText("已取消");
    await capture(page, "cancel", width!);
    expect(errors).toEqual([]);
  });
}

test("push_drawer_menu_modal_coexist_and_esc_respects_layers", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  await open(page, "default", true);
  const row = page.locator("tr[data-run-id]").nth(1);
  await row.click();
  await page.getByRole("button", { name: "Fixture menu", exact: true }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "扫描明细" })).toBeVisible();
  await page.getByRole("button", { name: "Fixture modal", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Fixture modal title" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Fixture modal title" })).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "扫描明细" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0); await expect(row).toBeFocused();
});

test("actual_application_router_loads_scan_page_and_mock_detail_budget", async ({ page }) => {
  for (const state of ["default", "detail", "budget"]) {
    await page.goto(`/#/scan?state=${state}`);
    await expect(page.locator('.p-scan[data-ready="true"]')).toBeVisible();
    if (state === "detail") await expect(page.getByRole("dialog", { name: "扫描明细" })).toBeVisible();
    if (state === "budget") await expect(page.locator(".p-scan__budget.is-danger")).toBeVisible();
  }
});

test("drawer_resize_1199_1200_preserves_single_layout_and_row_focus", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  await open(page);
  const row = page.locator("tr[data-run-id]").nth(1);
  await row.click();
  for (const width of [1199, 1200, 1024, 1280]) {
    await page.setViewportSize({ width, height: 820 });
    await expect(page.getByRole("dialog", { name: "扫描明细" })).toHaveCount(1);
    await expect(page.getByRole("dialog", { name: "扫描明细" })).toHaveAttribute("aria-modal", width < 1200 ? "true" : "false");
    expect(await page.locator(".l-drawer").count()).toBe(width < 1200 ? 0 : 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(row).toBeFocused();
});
