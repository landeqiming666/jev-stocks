import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
const prototype = "/@fs" + resolve("../../design/prototype/index.html");
for (const width of [1280, 1024]) {
  for (const state of ["default", "expanded", "search", "editor-error"]) {
    test(`${width} ${state} independent prototype <=1%`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: width === 1280 ? 820 : 700 });
      await page.goto(`${prototype}#/holdings?state=${state}&bare=1&platform=macos`);
      await expect(page.locator(".p-holdings")).toBeVisible();
      const baseline = info.snapshotPath(`${width}-${state}.png`);
      await mkdir(dirname(baseline), { recursive: true });
      await writeFile(baseline, await page.screenshot());
      await page.goto("/src/pages/holdings/dev-shell.html#/holdings");
      await expect(page.getByRole("button", { name: "展开 ZZAR" })).toBeVisible();
      if (state === "expanded" || state === "editor-error") {
        await page.getByRole("button", { name: "展开 ZZAR" }).click();
        await expect(page.getByText("控股股东长期持股，不会大幅减持", { exact: true })).toBeVisible();
      }
      if (state === "editor-error") {
        await page.getByRole("button", { name: "添加逻辑" }).click();
        await page.getByLabel("逻辑", { exact: true }).fill("   ");
        await page.getByRole("button", { name: "保存", exact: true }).click();
        await expect(page.getByText("逻辑内容不能为空")).toBeVisible();
      }
      if (state === "search") {
        await page.getByRole("combobox").fill("ze"); await expect(page.getByRole("option")).toHaveCount(4);
      }
      await expect(await page.screenshot()).toMatchSnapshot(`${width}-${state}.png`, { maxDiffPixelRatio: 0.01 });
    });
  }
}
