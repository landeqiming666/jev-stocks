import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test as base, type Page } from "@playwright/test";

export { expect };

const HERE = fileURLToPath(new URL(".", import.meta.url));
export const ROOT = resolve(HERE, "../../../..");

type Json = Record<string, unknown>;
type LineHandler = (line: string) => void;

export class CoreBridge {
  private child: ChildProcessWithoutNullStreams | null = null;
  private sequence = 0;
  private readonly pending = new Map<string, { resolve: (message: Json) => void; reject: (error: Error) => void; timer: NodeJS.Timeout }>();
  private readonly handlers = new Set<LineHandler>();
  private buffer = "";
  private exitCode: number | null = null;
  private failure: Error | null = null;
  private stderr = "";

  constructor(readonly dataDir: string, readonly memorySecrets = true) {}

  async start(timeoutMs = 30_000): Promise<void> {
    this.failure = null;
    this.stderr = "";
    const entry = this.memorySecrets
      ? [join(ROOT, "apps/desktop/e2e/acceptance/memory_core.py")]
      : ["-m", "sentinel"];
    const environment = { ...process.env };
    for (const name of ["JEV_API_KEY", "TYPESAFE_API_KEY", "SENTINEL_JEVDB_PATH", "JEV_ENDPOINT", "SENTINEL_CORE_CMD", "PYTHON_KEYRING_BACKEND"]) {
      delete environment[name];
    }
    const child = spawn(
      "uv",
      [
        "run",
        "--offline",
        "--project",
        join(ROOT, "core"),
        "python",
        ...entry,
        "--data-dir",
        this.dataDir,
        "--resource-dir",
        join(ROOT, "resources"),
        "--log-level",
        "WARN",
      ],
      {
        cwd: ROOT,
        env: {
          ...environment,
          SENTINEL_OFFLINE: "1",
          SENTINEL_CLOCK: "2026-11-02T08:35:00Z",
          PYTHONUNBUFFERED: "1",
          PYTHONUTF8: "1",
        },
        detached: true,
        windowsHide: true,
      },
    );
    this.child = child;
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", chunk => this.consume(String(chunk)));
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", chunk => { this.stderr = (this.stderr + String(chunk)).slice(-8192); });
    child.on("error", error => { this.failure = error; });
    child.on("exit", code => {
      this.exitCode = code ?? 0;
      for (const request of this.pending.values()) {
        clearTimeout(request.timer);
        request.reject(new Error(`core exited ${this.exitCode}`));
      }
      this.pending.clear();
    });
    try {
      await this.waitForNotification("app.ready", timeoutMs);
    } catch (error) {
      await this.terminate(child);
      this.child = null;
      throw error;
    }
  }

  private consume(chunk: string): void {
    this.buffer += chunk;
    let index = this.buffer.indexOf("\n");
    while (index >= 0) {
      const line = this.buffer.slice(0, index).trim();
      this.buffer = this.buffer.slice(index + 1);
      if (line) this.dispatch(line);
      index = this.buffer.indexOf("\n");
    }
  }

  private dispatch(line: string): void {
    let message: Json;
    try {
      message = JSON.parse(line) as Json;
    } catch {
      return;
    }
    if (typeof message.id === "string") {
      const waiter = this.pending.get(message.id);
      if (waiter) {
        this.pending.delete(message.id);
        clearTimeout(waiter.timer);
        waiter.resolve(message);
        return;
      }
    }
    // 页面客户端的响应与通知通过最小 IPC 转发。
    for (const handler of this.handlers) handler(line);
  }

  onLine(handler: LineHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  send(line: string): void {
    if (!this.child || this.exitCode !== null) throw new Error("core is not running");
    this.child.stdin.write(line + "\n");
  }

  request(method: string, params: Json = {}, timeoutMs = 30_000): Promise<Json> {
    this.sequence += 1;
    const id = `fixture-${this.sequence}`;
    return new Promise<Json>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timeout waiting for ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try { this.send(JSON.stringify({ jsonrpc: "2.0", id, method, params })); }
      catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  async result(method: string, params: Json = {}): Promise<Json> {
    const message = await this.request(method, params);
    if (message.error) throw new Error(`${method} failed: ${JSON.stringify(message.error)}`);
    return message.result as Json;
  }

  waitForNotification(method: string, timeoutMs: number): Promise<Json> {
    return new Promise<Json>((resolve, reject) => {
      const timer = setTimeout(() => {
        off();
        clearInterval(poll);
        reject(new Error(`timeout waiting for ${method}`));
      }, timeoutMs);
      const poll = setInterval(() => {
        if (this.failure || this.exitCode !== null) {
          clearTimeout(timer);
          clearInterval(poll);
          off();
          reject(this.failure ?? new Error(`core exited ${this.exitCode}: ${this.stderr}`));
        }
      }, 25);
      const off = this.onLine(line => {
        const message = JSON.parse(line) as Json;
        if (message.method === method) {
          clearTimeout(timer);
          clearInterval(poll);
          off();
          resolve(message);
        }
      });
    });
  }

  async restart(): Promise<void> {
    await this.stop();
    this.buffer = "";
    this.exitCode = null;
    await this.start();
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (!child) return;
    const deadline = Date.now() + 3000;
    if (this.exitCode === null && child.pid) {
      try {
        await this.request("app.shutdown", {}, 3000);
      } catch {
        // 超时或传输关闭后，结束本次启动的整个进程树。
      }
      await this.waitForExit(child, Math.max(1, deadline - Date.now()));
    }
    if (child.exitCode === null && child.signalCode === null) await this.terminate(child);
    this.child = null;
  }

  private waitForExit(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<void> {
    if (child.exitCode !== null || child.signalCode !== null || !child.pid) return Promise.resolve();
    return new Promise(resolve => {
      const finished = () => {
        clearTimeout(timer);
        child.off("exit", finished);
        resolve();
      };
      const timer = setTimeout(finished, timeoutMs);
      child.once("exit", finished);
    });
  }

  private async terminate(child: ChildProcessWithoutNullStreams): Promise<void> {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
    const taskkill = process.env.SystemRoot && join(process.env.SystemRoot, "System32", "taskkill.exe");
    if (taskkill && existsSync(taskkill)) {
      const result = spawnSync(taskkill, ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true, timeout: 5000, stdio: "ignore",
      });
      if ((result.error || result.status !== 0) && child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
    } else {
      try { process.kill(-child.pid, "SIGKILL"); }
      catch { if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL"); }
    }
    await this.waitForExit(child, 3000);
    if (child.exitCode === null && child.signalCode === null) throw new Error("core process did not exit after cleanup");
  }
}

export function tempDataDir(): string {
  return mkdtempSync(join(tmpdir(), "sentinel e2e 中文 "));
}

/** 安装最小 Tauri IPC 模拟：只转发 rpc_send、core_status 与事件监听。 */
export function installTauriShim(): void {
  type Payload = { event: string; id: number; payload: unknown };
  type Callback = (event: Payload) => void;
  interface Internals {
    convertFileSrc: (path: string) => string;
    transformCallback: (callback: Callback, once?: boolean) => number;
    unregisterCallback: (id: number) => void;
    invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
  }
  const holder = window as unknown as {
    __TAURI_INTERNALS__?: Internals;
    __TAURI_EVENT_PLUGIN_INTERNALS__?: { unregisterListener: (event: string, id: number) => void };
    __SENTINEL_TEST_EMIT__?: (message: { event: string; payload: unknown }) => void;
    __sentinelSend?: (line: string) => Promise<void>;
    __sentinelPoll?: () => Promise<string[]>;
  };
  const callbacks = new Map<number, Callback>();
  const listeners = new Map<string, Map<number, number>>();
  let sequence = 0;
  let status: { state: string; attempt: number } = { state: "ready", attempt: 0 };
  holder.__TAURI_INTERNALS__ = {
    convertFileSrc: path => path,
    transformCallback: (callback, once) => {
      const id = ++sequence;
      callbacks.set(
        id,
        once
          ? event => {
              callbacks.delete(id);
              callback(event);
            }
          : callback,
      );
      return id;
    },
    unregisterCallback: id => {
      callbacks.delete(id);
    },
    invoke: async (command, args) => {
      if (command === "plugin:event|listen") {
        const event = String(args?.event ?? "");
        const eventId = ++sequence;
        const entries = listeners.get(event) ?? new Map<number, number>();
        entries.set(eventId, Number(args?.handler));
        listeners.set(event, entries);
        return eventId;
      }
      if (command === "plugin:event|unlisten") {
        const entries = listeners.get(String(args?.event ?? ""));
        entries?.delete(Number(args?.eventId));
        return null;
      }
      if (command === "core_status") return status;
      if (command === "rpc_send") {
        await holder.__sentinelSend?.(String(args?.line ?? ""));
        return null;
      }
      throw new Error(`unsupported command: ${command}`);
    },
  };
  holder.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
    unregisterListener: (event, id) => {
      listeners.get(event)?.delete(id);
    },
  };
  holder.__SENTINEL_TEST_EMIT__ = message => {
    if (message.event === "core://status") status = message.payload as typeof status;
    for (const [eventId, callbackId] of listeners.get(message.event) ?? []) {
      callbacks.get(callbackId)?.({ event: message.event, id: eventId, payload: message.payload });
    }
  };
  // 轮询拉取核心输出，避免页面导航期间丢消息。
  setInterval(() => {
    void holder
      .__sentinelPoll?.()
      .then(lines => {
        for (const line of lines) {
          holder.__SENTINEL_TEST_EMIT__?.({ event: "core://message", payload: line });
        }
      })
      .catch(() => undefined);
  }, 25);
}

export const test = base.extend<{ core: CoreBridge; app: Page }>({
  // eslint-disable-next-line no-empty-pattern
  core: async ({}, use) => {
    const bridge = new CoreBridge(tempDataDir());
    try {
      await bridge.start();
      await use(bridge);
    } finally {
      await bridge.stop();
    }
  },
  app: [async ({ page, core }, use) => {
    let queue: string[] = [];
    const pageRequests = new Set<string>();
    await page.exposeFunction("__sentinelSend", (line: string) => {
      const message = JSON.parse(line) as Json;
      if (typeof message.id === "string") pageRequests.add(message.id);
      core.send(line);
    });
    await page.exposeFunction("__sentinelPoll", () => {
      const lines = queue;
      queue = [];
      return lines;
    });
    await page.addInitScript(installTauriShim);
    const off = core.onLine(line => {
      const message = JSON.parse(line) as Json;
      if (typeof message.id === "string") pageRequests.delete(message.id);
      queue.push(line);
    });
    try {
      // Vite 的首次转换使用启动预算，测试正文从空白页面开始。
      await page.goto("/#/today", { timeout: 60_000 });
      await expect(page.locator("[data-route][data-ready]")).toHaveAttribute("data-ready", "true");
      await page.goto("about:blank");
      await expect.poll(() => pageRequests.size).toBe(0);
      queue = [];
      await use(page);
    } finally {
      off();
    }
  }, { timeout: 60_000 }],
});

export async function openApp(page: Page, hash = "#/today"): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.getByRole("heading", { name: "投资逻辑哨兵" })).toBeVisible();
}

export async function emitStatus(page: Page, state: "starting" | "ready" | "restarting" | "failed"): Promise<void> {
  await page.evaluate(value => {
    const holder = window as unknown as {
      __SENTINEL_TEST_EMIT__?: (message: { event: string; payload: unknown }) => void;
    };
    holder.__SENTINEL_TEST_EMIT__?.({ event: "core://status", payload: { state: value, attempt: 1 } });
  }, state);
}
