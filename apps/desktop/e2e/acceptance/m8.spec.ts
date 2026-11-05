import { spawn, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { installTauriShim, ROOT } from "../real-core/fixture";

interface Message { id?: string; method?: string; result?: Record<string, unknown>; error?: { code: string }; }

test("M-8 real JEVDB scan reaches the production inbox and evidence drawer", async ({ page }) => {
  const directory = process.env.SENTINEL_M8_DIR;
  if (!directory) throw new Error("run acceptance.py --full --confirm-live-model-cost first");
  const interpreter = spawnSync("uv", ["run", "--project", join(ROOT, "core"), "python", "-c", "import sys; print(sys.executable)"], {
    cwd: ROOT, encoding: "utf8",
  });
  if (interpreter.status !== 0) throw new Error("cannot resolve core Python interpreter");
  const caseData = JSON.parse(readFileSync(join(directory, "case.json"), "utf8")) as {
    instrumentId: string; eventId: string; statement: string; from: string;
  };
  const child = spawn(interpreter.stdout.trim(), [
    join(ROOT, "scripts/acceptance_live.py"),
    "--serve", directory, "--confirm-live-model-cost",
  ], { cwd: ROOT, env: process.env });
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", () => undefined);
  const pending = new Map<string, (message: Message) => void>();
  let ready = false, exited = false, sequence = 0, buffer = "", queue: string[] = [];
  child.on("exit", () => { exited = true; });
  child.stdout.on("data", (chunk: string) => {
    buffer += chunk;
    let end = buffer.indexOf("\n");
    while (end >= 0) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 1);
      const message = JSON.parse(line) as Message;
      if (message.method === "app.ready") ready = true;
      const handler = message.id ? pending.get(message.id) : undefined;
      if (handler && message.id) {
        pending.delete(message.id);
        handler(message);
      } else {
        queue.push(line);
      }
      end = buffer.indexOf("\n");
    }
  });
  const request = (method: string, params: Record<string, unknown> = {}) => {
    const id = `m8-${++sequence}`;
    return new Promise<Record<string, unknown>>((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`core request timeout: ${method}`));
      }, 30_000);
      pending.set(id, message => {
        clearTimeout(timer);
        if (message.error) reject(new Error(`core error: ${message.error.code}`));
        else resolve(message.result ?? {});
      });
      child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    });
  };
  try {
    await expect.poll(() => ready || exited, { timeout: 35_000 }).toBe(true);
    expect(ready && !exited).toBe(true);
    const bootstrap = await request("app.bootstrap");
    expect(bootstrap.engine).toMatchObject({ requested: "jevdb", active: "jevdb" });
    await request("holdings.upsert", { instrumentId: caseData.instrumentId, quantity: "0.0000" });
    await request("thesis.create", { instrumentId: caseData.instrumentId, statement: caseData.statement });
    const started = await request("scan.start", { market: "us", from: caseData.from });
    let scan: Record<string, unknown> = {};
    await expect.poll(async () => {
      scan = await request("scan.status", { runId: started.runId });
      return scan.status !== "queued" && scan.status !== "running";
    }, { timeout: 300_000, intervals: [250, 500, 1000] }).toBe(true);
    const inbox = await request("inbox.list");
    const candidates = [...inbox.items as Record<string, unknown>[], ...inbox.uncertain as Record<string, unknown>[]];
    const selected = candidates.find(item => (item.event as { eventId: string }).eventId === caseData.eventId);
    if (!selected) {
      writeFileSync(join(directory, "result.json"), JSON.stringify({ bootstrap, scan, inbox }));
      throw new Error("real model produced no actionable decision for this fixed thesis; inspect results");
    }
    const detail = await request("decision.get", { decisionId: selected.decisionId });
    writeFileSync(join(directory, "result.json"), JSON.stringify({ bootstrap, scan, inbox, detail }, null, 2));
    expect(scan.status).toBe("succeeded");
    expect(detail.engine).toBe("jevdb");
    expect(detail.modelId).toBe("jev-1.14.0");
    await page.exposeFunction("__sentinelSend", (line: string) => { child.stdin.write(line + "\n"); });
    await page.exposeFunction("__sentinelPoll", () => { const lines = queue; queue = []; return lines; });
    await page.addInitScript(installTauriShim);
    await page.goto("/#/today");
    if (selected.relation === "uncertain") await page.locator("details").filter({ hasText: "系统拿不准" }).locator("summary").click();
    const card = page.locator("article").filter({ has: page.locator(`[id="t-${selected.decisionId}"]`) });
    await expect(card.locator(".c-decision__thesis")).toContainText(caseData.statement);
    await card.getByRole("button", { name: "查看原文" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/JEVDB/)).toBeVisible();
    await expect(dialog.getByText(/jev-1\.14\.0/)).toBeVisible();
    await expect(dialog.locator(".c-passage")).toContainText((detail.evidence as { text: string }).text);
    await page.screenshot({ path: join(directory, "evidence-drawer.png"), fullPage: true });
  } finally {
    if (!exited) {
      await request("app.shutdown", { force: true }).catch(() => undefined);
      await Promise.race([new Promise<void>(resolve => child.once("exit", () => resolve())),
        new Promise<void>(resolve => setTimeout(resolve, 3000))]);
      if (!exited) {
        child.kill("SIGKILL");
        await new Promise<void>(resolve => child.once("exit", () => resolve()));
      }
    }
    child.stdin.destroy();
    child.stdout.destroy();
    child.stderr.destroy();
  }
});
