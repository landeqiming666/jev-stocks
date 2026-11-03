import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { feedback } from "../../i18n/zh-CN/feedback";

const g = feedback.gallery;
const button = (page: import("@playwright/test").Page, name: string) => page.getByRole("button", { name, exact: true });
test("quietledger_feedback_screenshots_two_sizes_and_unknown_error_console_privacy", async ({ page }) => {
  const messages: string[] = [];
  page.on("console", message => messages.push(message.text()));
  page.on("pageerror", error => messages.push(error.message));
  for (const [width, height] of [[1280, 820], [1024, 700]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/src/components/feedback/dev-gallery.html");
    await expect(page.locator("[data-ready=true]")).toBeVisible();
    await button(page, g.offline).click(); await button(page, g.crash).click();
    await button(page, g.error).click(); await button(page, g.success).click();
    await expect(page.getByText(feedback.offline)).toBeVisible();
    await expect(page.getByText(/错误编号：[A-F0-9]{12}/)).toBeVisible();
    await expect(page.getByText(g.saved)).toBeVisible();
    await expect(page.getByText(g.failed)).toBeVisible();
    await page.screenshot({ path: resolve("../../docs/wp/status", `U-08-${width}.png`), animations: "disabled" });
    const geometry = await page.locator(".c-feedback-toasts").evaluate(element => {
      const box = element.getBoundingClientRect(), style = getComputedStyle(element);
      return { right: innerWidth - box.right, bottom: innerHeight - box.bottom, gap: style.gap,
        overflow: document.documentElement.scrollWidth > innerWidth };
    });
    expect(geometry).toEqual({ right: 24, bottom: 24, gap: "12px", overflow: false });
    await page.keyboard.press("Tab");
    await button(page, feedback.copy).focus();
    expect(await button(page, feedback.copy).evaluate(element => getComputedStyle(element).outlineWidth)).toBe("2px");
  }
  for (const secret of ["test-key-do-not-use", "private-thesis", "private-holding", "1234.5600"])
    expect(messages.join("\n")).not.toContain(secret);
});

test("real_menu_modal_drawer_escape_precedes_toast_and_focus_returns", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 });
  await page.goto("/src/components/feedback/dev-gallery.html");
  await button(page, g.error).click(); await button(page, g.menu).click();
  await expect(page.getByRole("menuitem")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(button(page, g.menu)).toBeFocused();
  await expect(page.getByText(g.failed)).toBeVisible();
  await button(page, g.drawer).click();
  await page.getByRole("dialog", { name: g.drawer }).getByRole("button", { name: g.modal }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: g.modal })).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: g.drawer })).toBeVisible();
  await expect(page.getByText(g.failed)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(button(page, g.drawer)).toBeFocused();
  await expect(page.getByText(g.failed)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText(g.failed)).toHaveCount(0);
});

test("duplicate_host_and_online_recovery_produce_one_toast_and_status_banner_does_not_cover_content", async ({ page }) => {
  await page.goto("/src/components/feedback/dev-gallery.html");
  await expect(page.locator("[data-ready=true]")).toBeVisible();
  await button(page, g.duplicate).click();
  await expect(page.locator("#feedback-root")).toHaveCount(1);
  await expect(page.locator(".c-feedback-toasts")).toHaveCount(1);
  await button(page, g.offline).click(); await button(page, g.offline).click();
  await expect(page.getByText(feedback.online, { exact: true })).toHaveCount(1);
  await button(page, feedback.coreRestarting).click();
  await expect(page.locator(".c-feedback-banners").getByText(feedback.coreRestarting)).toBeVisible();
  const geometry = await page.evaluate(() => ({
    banner: document.querySelector(".c-feedback-banners")!.getBoundingClientRect().bottom,
    main: document.querySelector(".l-main")!.getBoundingClientRect().top,
  }));
  expect(geometry.main).toBeGreaterThanOrEqual(geometry.banner);
  await button(page, feedback.coreReady).click();
  await expect(page.locator(".c-feedback-banners").getByText(feedback.coreReady)).toBeVisible();
  await expect(page.locator(".c-feedback-banners").getByText(feedback.coreReady)).toHaveCount(0, { timeout: 5000 });
});

test("clipboard_denial_has_manual_hint_and_diagnostic_has_exact_allowlist", async ({ page }) => {
  await page.goto("/src/components/feedback/dev-gallery.html");
  await button(page, g.crash).click();
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { configurable: true,
    value: { writeText: () => Promise.reject(new Error("test-key-do-not-use")) } }));
  await button(page, feedback.copy).click();
  await expect(page.getByText(feedback.copyFailed)).toBeVisible();
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
    writeText: (text: string) => { document.body.dataset.diagnostic = text; return Promise.resolve(); },
  } }));
  await button(page, feedback.copy).click();
  const diagnostic = await page.evaluate(() => JSON.parse(document.body.dataset.diagnostic!));
  expect(Object.keys(diagnostic)).toEqual(["code", "requestId", "appVersion", "protocolVersion", "time"]);
  expect(diagnostic.requestId).toMatch(/^[A-F0-9]{12}$/);
  expect(diagnostic.appVersion).toBe("0.1.0");
  await expect(page.getByText(feedback.copyFailed)).toHaveCount(0);
});

test("real_appshell_host_composition_reuses_root_and_exposes_baseline_offline_duplication", async ({ page }) => {
  await page.goto("/src/components/feedback/dev-shell.html#/today");
  await expect(page.locator("[data-ready=true]")).toBeVisible();
  await expect(page.locator("#feedback-root")).toHaveCount(1);
  await button(page, g.error).click();
  await expect(page.locator("#feedback-root").getByText(g.failed)).toBeVisible();
  await button(page, g.modal).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText(g.failed)).toBeVisible();
  await expect(button(page, g.modal)).toBeFocused();
  await button(page, g.offline).click();
  await expect(page.locator(".l-banners").getByText(feedback.offline)).toBeVisible();
  await expect(page.locator(".c-feedback-banners").getByText(feedback.offline)).toBeVisible();
  await expect(page.getByText(feedback.offline, { exact: true })).toHaveCount(2);
  await button(page, g.offline).click();
  await expect(page.getByText(feedback.offline, { exact: true })).toHaveCount(0);
  await expect(page.getByText(feedback.online, { exact: true })).toHaveCount(1);
  await button(page, g.crash).click();
  await expect(page.getByText(/错误编号：[A-F0-9]{12}/)).toBeVisible();
  expect(await page.locator(".l-top").evaluate(element => element.getBoundingClientRect().height)).toBe(56);
  expect(await page.locator(".l-status").evaluate(element => element.getBoundingClientRect().height)).toBe(28);
});
