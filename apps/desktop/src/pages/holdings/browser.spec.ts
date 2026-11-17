import { test, expect, type Page } from "@playwright/test";
import { resolve } from "node:path";
const entry = "/src/pages/holdings/dev-shell.html#/holdings";
const shots = resolve("../../docs/wp/status/U-03-shots");
interface Fixture {
  requests: { method: string; params: Record<string, unknown> }[];
  setConflict(): void; setArchiveFailure(): void; setPrices(value: string): void; setDelay(value: number): void;
  setSearch(value: unknown[] | null, ms?: number): void; setLimit(): void; setEmpty(): void;
}
declare global { interface Window { u03Fixture: Fixture } }
async function ready(page: Page) {
  await page.goto(entry);
  await expect(page.getByRole("button", { name: "展开 ZZAR" })).toBeVisible();
}
async function expand(page: Page) {
  const row = page.getByRole("button", { name: "展开 ZZAR" }).locator("xpath=ancestor::tr");
  await row.focus(); await row.press("Enter");
  await expect(page.getByText("控股股东长期持股，不会大幅减持", { exact: true })).toBeVisible();
}
for (const viewport of [{ width: 1280, height: 820 }, { width: 1024, height: 700 }]) {
  test.describe(`${viewport.width}x${viewport.height} synthetic browser`, () => {
    test.use({ viewport });
    test("real RouterView discovery, four screenshots and bounded overflow", async ({ page }) => {
      const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
      await ready(page);
      await page.screenshot({ path: `${shots}/${viewport.width}-default.png` });
      const sizes = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: innerWidth,
        table: document.querySelector(".c-table-wrap")!.scrollWidth, wrap: document.querySelector(".c-table-wrap")!.clientWidth }));
      expect(sizes.body).toBeLessThanOrEqual(sizes.viewport);
      await expand(page);
      await page.screenshot({ path: `${shots}/${viewport.width}-expanded.png` });
      await page.getByRole("button", { name: "编辑", exact: true }).first().click();
      const field = page.getByRole("textbox", { name: "逻辑", exact: true });
      await expect(field).toBeFocused(); await field.fill("中".repeat(501));
      await expect(field).toHaveAttribute("aria-invalid", "true");
      await expect(page.getByText("501 / 500")).toBeVisible();
      await page.screenshot({ path: `${shots}/${viewport.width}-editor-error.png` });
      await field.press("Escape"); await page.getByRole("button", { name: "放弃修改" }).click();
      await expect(page.getByRole("button", { name: "编辑", exact: true }).first()).toBeFocused();
      await page.getByRole("combobox").fill("ze");
      await expect(page.getByRole("option")).toHaveCount(4);
      await page.screenshot({ path: `${shots}/${viewport.width}-search.png` });
      expect(errors).toEqual([]);
    });
    test("keyboard search creates exact large quantity and notes, then watch-only", async ({ page }) => {
      await ready(page);
      const input = page.getByRole("combobox"); await input.fill("ze");
      await expect(page.getByRole("option")).toHaveCount(4);
      await input.press("ArrowDown"); await input.press("Enter");
      await expect(page.getByRole("textbox", { name: "数量", exact: true })).toBeFocused();
      await page.getByLabel("数量", { exact: true }).fill("99999999999999.9999");
      await page.getByLabel("成本（可选）").fill("99999999999999.9999");
      await page.getByLabel("备注（可选）").fill(" 🧪".trim().repeat(200));
      await page.getByLabel("数量", { exact: true }).press("Control+Enter");
      await expect(page.getByRole("button", { name: "收起 ZZNW" })).toBeVisible();
      const writes = await page.evaluate(() => window.u03Fixture.requests.filter(r => r.method === "holdings.upsert"));
      expect(writes[0]!.params.quantity).toBe("99999999999999.9999");
      expect(writes[0]!.params.avgCost).toBe("99999999999999.9999");
      await expect(page.getByText("99,999,999,999,999.9999")).toBeVisible();
      if (viewport.width === 1024) {
        const sizes = await page.evaluate(() => {
          const wrap = document.querySelector<HTMLElement>(".c-table-wrap")!;
          wrap.scrollLeft = 40;
          return { left: wrap.scrollLeft, width: document.body.scrollWidth, viewport: innerWidth };
        });
        expect(sizes.left).toBeGreaterThan(0); expect(sizes.width).toBeLessThanOrEqual(sizes.viewport);
      }
      await page.getByRole("button", { name: "编辑持仓" }).click();
      await page.getByLabel("数量", { exact: true }).fill("0");
      await page.getByLabel("成本（可选）").fill("");
      await page.getByRole("button", { name: "保存持仓" }).click();
      await expect(page.getByRole("button", { name: "收起 ZZNW" }).locator("xpath=ancestor::tr").getByText("关注")).toBeVisible();
    });
    test("optimistic conflict preserves draft through refresh and explicit baseline", async ({ page }) => {
      await ready(page); await expand(page);
      await page.getByRole("button", { name: "编辑", exact: true }).first().click();
      const field = page.getByLabel("逻辑", { exact: true }); await field.fill("我的未保存逻辑");
      await page.evaluate(() => window.u03Fixture.setConflict()); await field.press("Meta+Enter");
      await expect(page.getByText("这条逻辑已被修改，请刷新后再试")).toBeVisible();
      await expect(field).toHaveValue("我的未保存逻辑");
      await page.getByRole("button", { name: "刷新", exact: true }).click();
      await expect(page.getByText("服务器上的新逻辑")).toBeVisible();
      await expect(field).toHaveValue("我的未保存逻辑");
      await page.getByRole("button", { name: /以第 3 版为基础/ }).click();
      await page.getByRole("button", { name: "保存", exact: true }).click();
      await expect(page.getByText("我的未保存逻辑", { exact: true })).toBeVisible();
      const writes = await page.evaluate(() => window.u03Fixture.requests.filter(r => r.method === "thesis.update"));
      expect(writes.map(r => r.params.expectedVersion)).toEqual([2, 3]);
    });
    test("dirty route, Esc, modal focus trap and archive history", async ({ page }) => {
      await ready(page); await expand(page);
      await page.getByRole("button", { name: "版本历史" }).first().click();
      await expect(page.getByRole("dialog").getByText("控股股东长期持股", { exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button", { name: "版本历史" }).first()).toBeFocused();
      await page.getByRole("button", { name: "编辑", exact: true }).first().click();
      await page.getByLabel("逻辑", { exact: true }).fill("保留草稿");
      await page.getByRole("link", { name: "设置" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page).toHaveURL(/#\/holdings$/);
      await page.getByRole("button", { name: "继续编辑" }).click();
      await expect(page.getByLabel("逻辑", { exact: true })).toHaveValue("保留草稿");
      await page.getByLabel("逻辑", { exact: true }).press("Escape");
      const dialog = page.getByRole("dialog"); await dialog.getByRole("button", { name: "继续编辑" }).focus();
      await page.keyboard.press("Tab"); await expect(dialog.getByRole("button", { name: "放弃修改" })).toBeFocused();
      await page.keyboard.press("Escape"); await expect(dialog).not.toBeVisible();
      await page.getByLabel("逻辑", { exact: true }).press("Escape");
      await page.getByRole("button", { name: "放弃修改" }).click();
      await page.getByRole("button", { name: "归档", exact: true }).first().click();
      expect(await page.evaluate(() => window.u03Fixture.requests.filter(r => r.method === "thesis.archive").length)).toBe(0);
      await page.getByRole("button", { name: "确认归档" }).click();
      await expect(page.getByText("控股股东长期持股，不会大幅减持", { exact: true })).not.toBeVisible();
    });
    test("partial/offline refresh and failed archive remain honest", async ({ page }) => {
      await ready(page); await page.evaluate(() => window.u03Fixture.setPrices("partial"));
      await page.getByRole("button", { name: "刷新行情" }).click();
      await expect(page.getByText(/ZZFD.*行情刷新失败/)).toBeVisible();
      await expect(page.getByText(/ZZCL.*行情刷新失败/)).toBeVisible();
      await page.evaluate(() => window.u03Fixture.setPrices("offline"));
      await page.getByRole("button", { name: "刷新行情" }).click();
      await expect(page.getByText(/行情源暂时无法访问/).first()).toBeVisible();
      await expand(page); await page.evaluate(() => window.u03Fixture.setArchiveFailure());
      await page.getByRole("button", { name: "归档持仓" }).click();
      await page.getByRole("button", { name: "确认归档" }).click();
      await expect(page.getByRole("dialog").getByText("归档失败，请重试")).toBeVisible();
      await expect(page.getByRole("button", { name: "收起 ZZAR" })).toBeVisible();
    });
    test("stale asynchronous search and US filter", async ({ page }) => {
      await ready(page);
      await page.evaluate(() => window.u03Fixture.setSearch(null, 600));
      const input = page.getByRole("combobox"); await input.fill("ze");
      await expect.poll(() => page.evaluate(() => window.u03Fixture.requests.filter(r => r.method === "instruments.search").length)).toBe(1);
      await input.fill("qq"); await expect(page.getByRole("option")).toHaveCount(0);
      await expect(page.getByText("没有找到匹配的美股标的")).toBeVisible();
      await page.evaluate(() => window.u03Fixture.setSearch([{ instrumentId: "hk:ZZAR", market: "hk", symbol: "ZZAR" }], 40));
      await input.fill("hk"); await expect(page.getByText("没有找到匹配的美股标的")).toBeVisible();
      await expect(page.getByRole("option")).toHaveCount(0);
    });
  });
}
