import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const route = (query = "state=pending") => `/test-results/u02.html#/today?${query}`;
test("screenshots_required_four_states_at_1280_and_1024", async ({ page }) => {
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const [width, height] of [[1280, 820], [1024, 700]] as const) {
    await page.setViewportSize({ width, height });
    for (const state of ["pending", "empty", "scan_failed", "drawer-overturn"]) {
      await page.goto(route(state === "drawer-overturn" ? "state=pending&drawer=overturn" : `state=${state}`));
      await expect(page.locator(".p-today")).toHaveAttribute("data-ready", "true");
      if (state === "drawer-overturn") {
        await expect(page.locator("mark.c-evidence-mark")).toBeVisible();
        await expect(page.getByRole("dialog").locator("h2")).toBeFocused();
      }
      if (state === "scan_failed") await expect(page.locator(".p-today-alerts .c-banner--danger")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: resolve("../../docs/wp/status", `U-02-${state}-${width}.png`), animations: "disabled" });
    }
  }
  expect(errors).toEqual([]);
});
test("drawer_push_overlay_geometry_focus_escape_and_menu_above_push", async ({ page }) => {
  for (const width of [1280, 1200, 1199, 1024]) {
    await page.setViewportSize({ width, height: 820 });
    await page.goto(route());
    await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeVisible();
    const trigger = page.getByRole("button", { name: "查看原文" }).first();
    await trigger.click();
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expect(drawer.locator("h2")).toBeFocused();
    await expect(page.locator("mark")).toHaveText(/On October 29, 2026/);
    await drawer.evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
    if (width >= 1200) await page.locator(".l-drawer").evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
    const geometry = await page.evaluate(() => {
      const main = document.querySelector("main")!.getBoundingClientRect(), dialog = document.querySelector('[role="dialog"]')!.getBoundingClientRect();
      return { mainRight: main.right, left: dialog.left, width: dialog.width, asideLeft: document.querySelector(".l-drawer")?.getBoundingClientRect().left, aside: document.querySelectorAll(".l-drawer").length };
    });
    expect(geometry.width).toBeGreaterThanOrEqual(398);
    if (width >= 1200) {
      expect(geometry.mainRight).toBe(geometry.asideLeft); expect(geometry.aside).toBe(1);
      await expect(drawer).toHaveAttribute("aria-modal", "false");
      const menu = page.getByRole("button", { name: "更多处理方式" }).first();
      await menu.click(); await expect(page.getByRole("menuitem", { name: "准备卖出" })).toBeFocused();
      await page.keyboard.press("Escape"); await expect(drawer).toBeVisible(); await expect(menu).toBeFocused();
    } else {
      expect(geometry.mainRight).toBeGreaterThan(geometry.left); expect(geometry.aside).toBe(0);
      await expect(drawer).toHaveAttribute("aria-modal", "true");
      await drawer.getByRole("button", { name: "忽略", exact: true }).focus();
      await page.keyboard.press("Tab"); await expect(drawer.getByRole("button", { name: "关闭证据抽屉" })).toBeFocused();
      await page.keyboard.press("Shift+Tab"); await expect(drawer.getByRole("button", { name: "忽略", exact: true })).toBeFocused();
    }
    await page.keyboard.press("Escape"); await expect(drawer).toHaveCount(0); await expect(trigger).toBeFocused();
  }
});
test("action_rollback_success_reopen_and_intent_never_places_order", async ({ page }) => {
  await page.goto(route());
  const actions = page.getByRole("button", { name: "仍然成立", exact: true });
  await expect(actions).toHaveCount(3);
  await page.evaluate(() => window.__u02.failNext("decision.act"));
  await actions.first().click();
  await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeVisible();
  await expect(actions.first()).toBeFocused();
  await actions.first().click();
  await expect(page.getByRole("heading", { name: "今天有 2 件事需要你看一眼" })).toBeVisible();
  await expect(page.locator("#t-01JC8Z5V3Q00000000000094Z2")).toBeFocused();
  await page.getByText("已处理（2）", { exact: true }).click();
  await page.getByRole("button", { name: "重新打开" }).first().click();
  await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeVisible();
  await page.getByRole("button", { name: "更多处理方式" }).first().click();
  await page.getByRole("menuitem", { name: "准备卖出" }).click();
  await expect(page.getByRole("heading", { name: "今天有 2 件事需要你看一眼" })).toBeVisible();
  expect(await page.evaluate(() => window.__u02.requests.some(r => r.method.startsWith("paper.")))).toBe(false);
});
test("all_nine_page_and_six_drawer_fixtures_and_demo_unconfigured_cache", async ({ page }) => {
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  for (const state of ["pending", "empty", "loading", "scanning", "scan_failed", "offline", "no_holdings", "unconfigured", "engine_fallback"]) {
    await page.goto(route(`state=${state}`));
    await expect(page.locator(".p-today")).toBeVisible();
    if (state === "loading") await expect(page.locator(".c-skeleton--card")).toHaveCount(3);
    else await expect(page.locator(".p-today")).toHaveAttribute("data-ready", "true");
    if (state === "scanning") await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "9");
    if (["offline", "unconfigured", "no_holdings"].includes(state)) await expect(page.getByRole("button", { name: "立即扫描" })).toBeDisabled();
  }
  for (const drawer of ["overturn", "weaken", "uncertain", "title_only", "processed", "not_found"]) {
    await page.goto(route(`state=pending&drawer=${drawer}`));
    await expect(page.getByRole("dialog")).toBeVisible();
    if (drawer === "not_found") {
      await expect(page.getByText("没有找到这条判定")).toBeVisible();
      await expect(page.getByRole("dialog").getByRole("button")).toHaveCount(1);
    } else {
      await expect(page.getByRole("list", { name: "五个问题的概率" }).locator("li")).toHaveCount(5);
      expect(await page.locator(".c-drawer__body").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      if (drawer === "title_only") await expect(page.getByText("仅依据标题判定")).toBeVisible();
      if (drawer === "processed") await expect(page.getByRole("dialog").getByRole("button", { name: "重新打开" })).toBeVisible();
    }
  }
  await page.goto(route("state=pending&fixture=demo-unconfigured"));
  await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeVisible();
  await expect(page.getByText("系统拿不准的 1 条")).toBeVisible();
  await expect(page.getByRole("button", { name: "立即扫描" })).toBeDisabled();
  await page.getByRole("button", { name: "查看原文" }).first().click();
  await expect(page.locator("mark")).toBeVisible();
  expect(errors).toEqual([]);
});
test("scan_cancel_uses_current_run_and_finished_refreshes_retained_list", async ({ page }) => {
  await page.goto(route("state=scanning"));
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "9");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("button", { name: "正在取消" })).toBeDisabled();
  expect(await page.evaluate(() => window.__u02.requests.filter(r => r.method === "scan.cancel"))).toHaveLength(1);
  await page.evaluate(async () => {
    const run = await window.__u02.client.call("scan.status", { runId: "01JC8Z5V3Q000000000000C6M5" });
    window.__u02.client.injectNotification("scan.finished", { ...run, status: "cancelled", finishedAt: "2026-11-02T00:35:00Z" });
  });
  await expect(page.getByRole("button", { name: "立即扫描" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeVisible();
});
test("keyboard_page_title_tab_order_card_open_and_processing", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 });
  await page.goto(route());
  await expect(page.getByRole("heading", { name: "今天有 3 件事需要你看一眼" })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "立即扫描" })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "查看原文" }).first()).toBeFocused();
  await page.keyboard.press("Enter"); await expect(page.getByRole("dialog").locator("h2")).toBeFocused();
  await page.keyboard.press("Escape"); await expect(page.getByRole("button", { name: "查看原文" }).first()).toBeFocused();
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "仍然成立" }).first()).toBeFocused();
  await page.keyboard.press("Enter"); await expect(page.locator("#t-01JC8Z5V3Q00000000000094Z2")).toBeFocused();
});
test("server_scan_conflict_disables_start_then_real_progress_exposes_cancel", async ({ page }) => {
  await page.goto(route());
  await expect(page.getByRole("button", { name: "立即扫描" })).toBeEnabled();
  await page.evaluate(() => window.__u02.client.setExample("scan.start", "conflict"));
  await page.getByRole("button", { name: "立即扫描" }).click();
  await expect(page.getByRole("button", { name: "立即扫描" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "立即扫描" })).toHaveAttribute("title", "扫描正在进行");
  await page.evaluate(() => window.__u02.client.injectNotification("scan.progress"));
  await expect(page.getByRole("button", { name: "取消", exact: true })).toBeEnabled();
});
