import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

for (const [width, height] of [[1280, 820], [1024, 700]] as const) {
  for (const state of ["pending", "empty", "scan_failed", "drawer-overturn"]) {
    test(`pixel_${state}_${width}_max_diff_one_percent`, async ({ page, context }, info) => {
      const query = state === "drawer-overturn" ? "state=pending&drawer=overturn" : `state=${state}`;
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const prototype = await context.newPage();
      await prototype.setViewportSize({ width, height });
      await prototype.emulateMedia({ reducedMotion: "reduce" });
      await prototype.goto(`${pathToFileURL(resolve("../../design/prototype/index.html")).href}#/today?${query}&bare=1`);
      await prototype.locator('[data-ready="true"]').waitFor();
      await prototype.evaluate(() => document.fonts.ready);
      await prototype.locator(".c-drawer").evaluateAll(elements => Promise.all(elements.flatMap(element => element.getAnimations()).map(animation => animation.finished)));
      const expected = await prototype.screenshot({ animations: "disabled" });
      const path = info.snapshotPath(`${state}-${width}.png`);
      await mkdir(dirname(path), { recursive: true }); await writeFile(path, expected);
      await page.goto(`/test-results/u02.html#/today?${query}`);
      await page.locator('.p-today[data-ready="true"]').waitFor();
      if (state === "drawer-overturn") await page.locator("mark").waitFor();
      await page.evaluate(async () => { await document.fonts.ready; (document.activeElement as HTMLElement)?.blur(); });
      expect(await page.screenshot({ animations: "disabled" })).toMatchSnapshot(`${state}-${width}.png`, { maxDiffPixelRatio: 0.01 });
    });
  }
}
