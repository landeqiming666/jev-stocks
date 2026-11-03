import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

test("real_shell_two_viewports_navigation_unknown_data_and_screenshots", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  for (const [width, height] of [[1280, 820], [1024, 700]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/#/today");
    await expect(page.getByText("页面正在搭建。")).toBeVisible();
    await expect(page.getByText("界面预览 · 示例数据")).toBeVisible();
    await expect(page.getByText("市场状态未就绪")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const sizes = await page.evaluate(() => {
      const box = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      return [box(".l-nav").width, box(".l-top").height, box(".l-status").height];
    });
    expect(sizes).toEqual([68, 56, 28]);
    for (const label of ["持仓", "交易", "风险", "扫描", "设置", "今天"]) {
      await page.getByRole("link", { name: label, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: label })).toBeFocused();
      await expect(page.getByRole("link", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
      expect(await page.locator('[aria-current="page"]').count()).toBe(1);
    }
    await page.screenshot({ path: resolve("../../docs/wp/status", `U-00-${width}.png`), animations: "disabled" });
    await page.goto("/#/missing?unknown=a%26b");
    await expect(page.getByRole("heading", { level: 1, name: "今天" })).toBeFocused();
    expect(new URL(page.url()).hash).toContain("unknown=a%26b");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "去设置" })).toBeFocused();
  }
  expect(errors).toEqual([]);
});

test("page_frame_overlay_and_push_at_1199_and_1200_without_overflow", async ({ page }) => {
  for (const width of [1024, 1199, 1200, 1280]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/test-results/u00-frame.html");
    await expect(page.getByRole("heading", { name: "Frame test" })).toBeVisible();
    await page.locator(".l-drawer").evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
    const rects = await page.evaluate(() => {
      const main = document.querySelector("main")!.getBoundingClientRect();
      const aside = document.querySelector("aside")!.getBoundingClientRect();
      const root = document.querySelector(".l-content")!.getBoundingClientRect();
      const scrim = getComputedStyle(document.querySelector(".l-scrim")!).display;
      return { mainRight: main.right, asideLeft: aside.left, asideWidth: aside.width, rootWidth: root.width,
        scrim, overflow: document.documentElement.scrollWidth > innerWidth };
    });
    expect(rects.asideWidth).toBe(400);
    expect(rects.overflow).toBe(false);
    if (width < 1200) { expect(rects.mainRight).toBeGreaterThan(rects.asideLeft); expect(rects.scrim).toBe("block"); }
    else { expect(rects.mainRight).toBe(rects.asideLeft); expect(rects.scrim).toBe("none"); }
  }
});

test("reduced_motion_disables_all_shell_and_drawer_animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const url of ["/#/today", "/test-results/u00-frame.html"]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => [...document.querySelectorAll("*")].every(element => {
      const style = getComputedStyle(element);
      return style.animationName === "none" && style.transitionDuration === "0s";
    }))).toBe(true);
  }
});
