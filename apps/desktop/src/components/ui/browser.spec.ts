import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { common } from "../../i18n/zh-CN/common";

test("pageframe_drawer_real_push_overlay_geometry_and_two_component_screenshots", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  for (const [width, height] of [[1280, 820], [1024, 700], [1199, 820], [1200, 820]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/test-results/u01.html");
    await expect(page.getByRole("dialog", { name: "Drawer" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Drawer", exact: true })).toBeFocused();
    const geometry = await page.evaluate(() => {
      const box = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const dialog = box(".c-drawer"), main = box(".l-main"), content = box(".l-content");
      const aside = document.querySelector(".l-drawer")?.getBoundingClientRect();
      return { width: dialog.width, left: dialog.left, right: dialog.right, top: dialog.top, bottom: dialog.bottom,
        mainWidth: main.width, mainRight: main.right, contentWidth: content.width, asideWidth: aside?.width,
        asideLeft: aside?.left, layoutCount: document.querySelectorAll(".l-drawer").length,
        overflow: document.documentElement.scrollWidth > innerWidth };
    });
    expect(geometry.right).toBe(width);
    expect(geometry.top).toBe(56);
    expect(geometry.bottom).toBe(height - 28);
    expect(geometry.overflow).toBe(false);
    if (width >= 1200) {
      expect(geometry.asideWidth).toBe(400);
      expect(geometry.layoutCount).toBe(1);
      expect(geometry.mainRight).toBe(geometry.asideLeft);
      expect(geometry.mainWidth).toBe(geometry.contentWidth - 400);
      expect(geometry.width).toBeGreaterThanOrEqual(398);
      await expect(page.locator(".l-drawer .c-drawer__head")).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "false");
    } else {
      expect(geometry.width).toBe(400);
      expect(geometry.layoutCount).toBe(0);
      expect(geometry.mainWidth).toBe(geometry.contentWidth);
      expect(geometry.mainRight).toBeGreaterThan(geometry.left);
      await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
      await expect(page.locator(".c-drawer-scrim")).toBeVisible();
    }
    if (width === 1280 || width === 1024) {
      await page.screenshot({ path: resolve("../../docs/wp/status", `U-01-${width}.png`), animations: "disabled" });
    }
    await page.getByRole("button", { name: common.closeDrawer }).click();
    expect(await page.locator(".l-main").evaluate(element => element.getBoundingClientRect().width)).toBe(geometry.contentWidth);
  }
  expect(errors).toEqual([]);
});

test("strictmode_browser_nested_top_escape_focus_restoration_and_overlay_tab_cycle", async ({ page }) => {
  for (const width of [1280, 1024]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("/test-results/u01.html");
    await page.getByRole("button", { name: common.closeDrawer }).click();
    const trigger = page.getByRole("button", { name: "Drawer", exact: true });
    await trigger.click();
    const modalTrigger = page.getByRole("dialog", { name: "Drawer" }).getByRole("button", { name: "Modal" });
    await modalTrigger.click();
    const modal = page.getByRole("dialog", { name: "Modal" });
    await expect(modal.getByRole("button", { name: common.cancel })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(modal.getByRole("button", { name: common.confirm })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(modal.getByRole("button", { name: common.cancel })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "Drawer" })).toBeVisible();
    await expect(modalTrigger).toBeFocused();
    if (width < 1200) {
      await page.getByRole("dialog").getByRole("button", { name: common.close, exact: true }).focus();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: common.closeDrawer })).toBeFocused();
    } else {
      await page.getByRole("dialog").getByRole("button", { name: common.close, exact: true }).focus();
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => !document.querySelector(".c-drawer")!.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  }
});

test("component_keyboard_menu_segments_search_table_toggle_and_shell_css_isolation", async ({ page }) => {
  await page.goto("/test-results/u01.html");
  await page.getByRole("button", { name: common.closeDrawer }).click();
  const first = page.getByRole("radio", { name: common.market.us });
  await first.focus(); await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: common.market.hk })).toBeFocused();
  await expect(page.getByRole("radio", { name: common.market.hk })).toHaveAttribute("aria-checked", "true");
  expect(await first.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(32);
  const menuTrigger = page.getByRole("button", { name: "Menu", exact: true });
  await menuTrigger.click();
  await expect(page.getByRole("menuitem", { name: common.save })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: common.close })).toBeFocused();
  await page.keyboard.press("Home"); await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(menuTrigger).toBeFocused();
  await menuTrigger.click(); await page.keyboard.press("Escape");
  await expect(menuTrigger).toBeFocused();
  await expect(page.getByRole("combobox", { name: "Search" })).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("radio", { name: common.chartTableView }).click();
  await expect(page.getByRole("table", { name: common.chartUnits.correlation })).toBeVisible();
  await expect(page.getByRole("table", { name: common.chartUnits.explainedVariance })).toContainText("46.0%");
  await expect(page.getByRole("table", { name: common.chartUnits.correlation })).toContainText("-0.42");
  await expect(page.getByRole("table", { name: common.chartUnits.correlation })).toContainText(common.chartNoData);
  await page.getByRole("radio", { name: common.chartVisualView }).click();
  await expect(page.getByRole("img", { name: common.chartUnits.correlation })).toBeVisible();
  const shell = await page.locator(".l-top .c-engine").evaluate(element => {
    const style = getComputedStyle(element);
    return [style.borderLeftWidth, style.paddingLeft, element.hasAttribute("data-ui")];
  });
  expect(shell).toEqual(["0px", "0px", false]);
});

test("modal_backdrop_closes_reduced_motion_removes_animations_and_transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/test-results/u01.html");
  await page.getByRole("button", { name: common.closeDrawer }).click();
  await page.getByRole("button", { name: "Modal", exact: true }).click();
  await page.locator(".c-modal-scrim").click({ position: { x: 10, y: 10 } });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modal", exact: true })).toBeFocused();
  expect(await page.evaluate(() => [...document.querySelectorAll("*")].every(element => {
    const style = getComputedStyle(element);
    return style.animationName === "none" && style.transitionDuration === "0s";
  }))).toBe(true);
});

test("main_menu_above_open_pageframe_push_drawer_has_focus_and_escapes_without_closing_drawer", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  await page.goto("/test-results/u01.html");
  const drawer = page.getByRole("dialog", { name: "Drawer" });
  await expect(drawer).toHaveAttribute("aria-modal", "false");
  const trigger = page.getByRole("button", { name: "Menu", exact: true });
  await trigger.click();
  await expect(page.getByRole("menuitem", { name: common.save })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: common.close })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.getByRole("menuitem", { name: common.save })).toBeFocused();
  await page.keyboard.press("End");
  await expect(page.getByRole("menuitem", { name: common.close })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(drawer).toBeVisible();
  await expect(trigger).toBeFocused();
});
