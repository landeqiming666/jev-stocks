import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const report = fileURLToPath(new URL("../../../../../docs/wp/status/", import.meta.url));
mkdirSync(report, { recursive: true });
async function open(page: Page, state = "default") {
  await page.goto("about:blank");
  await page.goto(`/src/pages/trading/dev-gallery.html#/trading?state=${state}`);
  await expect(page.locator(".p-trading[data-ready=true]")).toBeVisible();
}
async function select(page: Page) {
  const search = page.getByRole("combobox", { name: "标的" });
  await search.fill("zz"); await expect(page.getByRole("listbox")).toBeVisible();
  await search.press("ArrowDown"); await search.press("Enter");
}
async function capture(page: Page, state: string, width: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `${report}U-05-${width}-${state}.png` });
}
for (const [width, height] of [[1280, 820], [1024, 700]]) {
  test(`states and keyboard at ${width}x${height}`, async ({ page }) => {
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width: width!, height: height! }); await open(page);
    await expect(page.getByRole("heading", { name: "交易", exact: true })).toBeFocused();
    await expect(page.getByText("权益", { exact: true })).toBeVisible();
    await capture(page, "default", width!);
    await page.getByRole("tab", { name: "挂单", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "成交", exact: true })).toHaveAttribute("aria-selected", "true");
    await select(page);
    await page.getByRole("radio", { name: "买入" }).focus(); await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("radio", { name: "卖出" })).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("ArrowLeft");
    await page.getByLabel("数量（股）").fill("0"); await page.getByLabel("数量（股）").press("Enter");
    await expect(page.getByText("数量必须是 1 至 1,000,000 的正整数")).toBeVisible();
    await capture(page, "form-error", width!);
    await open(page, "error-cash"); await select(page); await page.getByRole("button", { name: "提交订单" }).click();
    await expect(page.getByRole("tab", { name: "历史订单" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("tr.is-selected")).toContainText("已拒绝");
    await expect(page.locator("tr.is-selected")).toContainText("$92,025.99");
    await expect(page.locator(".c-toast")).toHaveCount(0); await capture(page, "rejected", width!);
    await page.getByRole("tab", { name: "挂单" }).click();
    await expect(page.getByRole("tab", { name: "挂单" })).toHaveAttribute("aria-selected", "true");
    await open(page); await page.getByRole("button", { name: "下一交易日" }).click();
    await expect(page.locator(".p-trading__clock")).toContainText("2026-10-30");
    await expect(page.locator(".c-toast")).toContainText("1 笔成交"); await capture(page, "advance", width!);
    await page.getByRole("button", { name: "下一交易日" }).click();
    await expect(page.locator(".c-banner--warn")).toBeVisible();
    await expect(page.locator(".p-trading__clock")).toContainText("2026-10-30"); await capture(page, "no-price", width!);
    await open(page); const reset = page.getByRole("button", { name: "重置账户", exact: true }); await reset.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByLabel("输入账户名")).toBeFocused();
    await expect(page.getByRole("button", { name: "确认重置", exact: true })).toBeDisabled();
    await page.keyboard.press("Escape"); await expect(reset).toBeFocused(); await reset.click();
    await page.getByLabel("输入账户名").fill("回放账户 A");
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", { name: "确认重置", exact: true })).toBeFocused();
    await page.keyboard.press("Tab"); await expect(page.getByLabel("输入账户名")).toBeFocused();
    await capture(page, "reset", width!);
    await page.getByRole("button", { name: "确认重置", exact: true }).click(); await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText("没有待成交的订单。")).toBeVisible();
    await open(page, "no_account"); await capture(page, "no-account", width!);
    await page.getByLabel("账户名称").fill("新账户");
    await page.getByLabel("初始现金（美元）").fill("100000000000000");
    await page.getByRole("button", { name: "创建账户", exact: true }).click();
    await expect(page.getByText("初始现金须为正数，整数最多 14 位，小数最多 4 位")).toBeVisible();
    expect(await page.evaluate(() => window.u05Calls.filter(call => call.method === "paper.createAccount").length)).toBe(0);
    await page.getByLabel("初始现金（美元）").fill("100000.0000");
    await page.getByRole("button", { name: "创建账户", exact: true }).click();
    await expect(page.getByLabel("账户", { exact: true })).toHaveValue("synthetic-account-1");
    await expect(page.locator(".p-trading__clock")).toContainText("2026-10-29");
    expect(errors).toEqual([]);
  });
}
test("timeout preserves key and looks up before retry; reset failure keeps confirmation", async ({ page }) => {
  await open(page, "timeout"); await select(page); await page.getByRole("button", { name: "提交订单" }).dblclick();
  await expect(page.getByRole("button", { name: "查询并重试原订单" })).toBeVisible();
  await expect(page.getByLabel("数量（股）")).toBeDisabled();
  await page.getByRole("button", { name: "查询并重试原订单" }).click();
  await expect(page.getByRole("button", { name: "提交订单" })).toBeVisible();
  const calls = await page.evaluate(() => window.u05Calls.filter(call => ["paper.order.place", "paper.orders"].includes(call.method)));
  const places = calls.filter(call => call.method === "paper.order.place"); expect(places).toHaveLength(2);
  expect(places[0]!.params.idempotencyKey).toBe(places[1]!.params.idempotencyKey);
  expect(calls.some(call => call.method === "paper.orders" && call.params.idempotencyKey === places[0]!.params.idempotencyKey)).toBe(true);
  await open(page, "reset-failure"); await page.getByRole("button", { name: "重置账户", exact: true }).click();
  await page.getByLabel("输入账户名").fill("回放账户 A"); await page.getByRole("button", { name: "确认重置", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("备份失败"); await expect(page.getByLabel("输入账户名")).toHaveValue("回放账户 A");
});
