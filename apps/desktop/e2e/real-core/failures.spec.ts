import type { ChildProcess } from "node:child_process";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { CoreBridge, expect, test, emitStatus, tempDataDir } from "./fixture";

test("failed fixture startup reaps its process", async () => {
  const blocked = join(tempDataDir(), "file instead of data directory");
  writeFileSync(blocked, "controlled startup failure", "utf8");
  const bridge = new CoreBridge(blocked);
  const started = bridge.start(5000);
  const child = (bridge as unknown as { child: ChildProcess }).child;
  await expect(started).rejects.toThrow(/core exited/);
  await bridge.stop();
  expect(child.exitCode !== null || child.signalCode !== null).toBe(true);
});

test("restarting banner keeps the cached inbox visible", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();

  await emitStatus(app, "restarting");
  await expect(app.getByText("核心进程正在重启…")).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();

  await emitStatus(app, "ready");
  await expect(app.getByText("核心进程正在重启…")).toBeHidden({ timeout: 8_000 });
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
});

test("failed core offers a retry action", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
  await emitStatus(app, "failed");
  await expect(app.getByText("核心进程未能启动，请重试。")).toBeVisible();
  await expect(app.getByRole("button", { name: "重试" }).first()).toBeVisible();
});

test("restarting the real core keeps local demo data", async ({ core, app }) => {
  await core.result("demo.load");
  await app.goto("/#/today");
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();

  await core.restart();
  await app.reload();
  await expect(app.getByRole("heading", { name: /今天有 2 件事/ })).toBeVisible();
  await expect(app.getByText("ZZAR").first()).toBeVisible();
});

test("unknown method surfaces a visible error", async ({ core }) => {
  const response = await core.request("no.such.method");
  expect(response.error).toMatchObject({ code: "INVALID_ARGUMENT" });
});
