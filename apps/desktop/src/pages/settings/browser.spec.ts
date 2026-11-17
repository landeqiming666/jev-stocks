import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
const gallery = "/src/pages/settings/dev-gallery.html#/settings";
test("quiet_ledger_six_sections_three_states_two_sizes", async ({ page }) => {
  for (const [width, height] of [[1280, 820], [1024, 700]] as const) {
    await page.setViewportSize({ width, height });
    for (const state of ["configured", "unconfigured", "test-ok"]) {
      await page.goto(`${gallery}?state=${state}`);
      await expect(page.getByRole("heading", { name: "密钥与联系方式" })).toBeVisible();
      if (state === "test-ok") await expect(page.getByText("日常运行可用")).toBeVisible();
      if (state === "unconfigured") await expect(page.getByLabel("Jev 密钥")).toBeVisible();
      await expect(page.locator(".p-settings__group")).toHaveCount(6);
      expect(await page.locator(".p-settings__group h2").first().evaluate(element => getComputedStyle(element).fontSize)).toBe("18px");
      const overflow = await page.locator(".l-main").evaluate(element => element.scrollWidth > element.clientWidth);
      expect(overflow).toBe(false);
      await page.screenshot({ path: resolve("../../docs/wp/status", `U-07-${state}-${width}.png`), animations: "disabled" });
      if (state === "test-ok") {
        await page.getByRole("heading", { name: "语义引擎" }).evaluate(element => element.closest("section")!.scrollIntoView({ block: "start" }));
        await page.screenshot({ path: resolve("../../docs/wp/status", `U-07-${state}-${width}-checks.png`), animations: "disabled" });
      }
      await page.getByRole("heading", { name: "隐私与外联" }).evaluate(element => element.closest("section")!.scrollIntoView({ block: "start" }));
      await expect(page.getByRole("table", { name: "外联域名" }).getByRole("row")).toHaveCount(6);
      await page.screenshot({ path: resolve("../../docs/wp/status", `U-07-${state}-${width}-detail.png`), animations: "disabled" });
      if (width === 1024) {
        await page.locator(".l-main").evaluate(element => { element.scrollTop = element.scrollHeight; });
        await page.screenshot({ path: resolve("../../docs/wp/status", `U-07-${state}-${width}-about.png`), animations: "disabled" });
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    }
  }
});
test("keyboard_clear_confirm_escape_restores_focus_and_engine_arrows", async ({ page }) => {
  await page.goto(`${gallery}?state=configured`);
  const clear = page.getByRole("button", { name: "清除", exact: true });
  await clear.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "确认清除" })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await page.keyboard.press("Escape"); await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(clear).toBeFocused();
  await page.getByRole("radio", { name: "自动（推荐）", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "JEVDB", exact: true })).toBeChecked();
  await expect(page.getByText("JEVDB 不可用，将阻止扫描")).toBeVisible();
});
test("local_password_no_attribute_no_clipboard_no_console", async ({ page }) => {
  const messages: string[] = [];
  page.on("console", message => messages.push(message.text()));
  page.on("pageerror", error => messages.push(error.message));
  await page.goto(`${gallery}?state=unconfigured`);
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: () => { throw new Error("clipboard must not be used"); } } });
  });
  const input = page.getByLabel("Jev 密钥");
  await input.fill("test-key-do-not-use");
  await expect(input).toHaveAttribute("type", "password");
  expect(await input.getAttribute("value")).toBeNull();
  expect(await page.locator("body").innerHTML()).not.toContain("test-key-do-not-use");
  await page.getByRole("button", { name: "保存密钥" }).click();
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "替换", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "替换", exact: true }).click();
  await expect(page.getByLabel("Jev 密钥")).toHaveValue("");
  expect(messages.join("\n")).not.toContain("test-key-do-not-use");
  expect(messages.filter(message => message.includes("Error"))).toEqual([]);
});
test("email_budget_lookback_field_errors_and_draft_survives_engine_save", async ({ page }) => {
  await page.goto(`${gallery}?state=configured`);
  const email = page.getByLabel("SEC 联系邮箱");
  await email.fill("abc"); await page.getByRole("button", { name: "保存邮箱" }).click();
  await expect(page.getByText("联系邮箱格式不正确", { exact: true })).toBeVisible();
  await expect(email).toHaveAttribute("aria-invalid", "true");
  await email.fill("draft@example.com"); await page.getByRole("radio", { name: "Jev 直连", exact: true }).click();
  await expect(email).toHaveValue("draft@example.com");
  await page.getByLabel("每日 token 上限").fill("999");
  await page.getByLabel("首次扫描回看天数").fill("31");
  await page.getByRole("button", { name: "保存预算" }).click();
  await expect(page.getByText("请输入 10000 至 50000000 的整数。", { exact: true })).toBeVisible();
  await expect(page.getByText("请输入 1 至 30 的整数。", { exact: true })).toBeVisible();
});
test("production_page_hash_does_not_override_unconfigured_rpc", async ({ page }) => {
  await page.route("**/src/rpc/index.ts", async route => {
    const response = await route.fetch();
    const source = await response.text();
    expect(source).toContain("createMockRpcClient({})");
    await route.fulfill({ response, body: source.replace("createMockRpcClient({})", 'createMockRpcClient({ scenario: "settings.unconfigured" })') });
  });
  await page.goto("/#/settings?state=test-ok&focusModal=do-not-reflect");
  await expect(page.getByLabel("Jev 密钥")).toBeVisible();
  await expect(page.getByText("请先填写 Jev 密钥和 SEC 联系邮箱，扫描无法开始。", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "连接测试结果" })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.locator("body").innerHTML()).not.toContain("do-not-reflect");
});
