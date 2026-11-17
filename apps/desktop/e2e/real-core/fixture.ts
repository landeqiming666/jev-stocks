import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdtempSync } from "node:fs";
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
  private readonly pending = new Map<string, (message: Json) => void>();
  private readonly handlers = new Set<LineHandler>();
  private buffer = "";
  private exitCode: number | null = null;

  constructor(readonly dataDir: string, readonly memorySecrets = false) {}

  async start(): Promise<void> {
    const entry = this.memorySecrets
      ? [join(ROOT, "apps/desktop/e2e/acceptance/memory_core.py")]
      : ["-m", "sentinel"];
    const child = spawn(
      "uv",
      [
        "run",
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
          ...process.env,
          SENTINEL_OFFLINE: "1",
          SENTINEL_CLOCK: "2026-11-02T08:35:00Z",
          PYTHONUNBUFFERED: "1",
        },
      },
    );
    this.child = child;
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", chunk => this.consume(String(chunk)));
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", () => undefined);
    child.on("exit", code => {
      this.exitCode = code ?? 0;
    });
    await this.waitForNotification("app.ready", 30_000);
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
        waiter(message);
      }
    }
    // 响应也要交给页面，页面自己的客户端按 id 匹配。
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

  request(method: string, params: Json = {}): Promise<Json> {
    this.sequence += 1;
    const id = `r-${String(this.sequence).padStart(2, "0")}`;
    return new Promise<Json>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timeout waiting for ${method}`));
      }, 30_000);
      this.pending.set(id, message => {
        clearTimeout(timer);
        resolve(message);
      });
      this.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
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
        reject(new Error(`timeout waiting for ${method}`));
      }, timeoutMs);
      const off = this.onLine(line => {
        const message = JSON.parse(line) as Json;
        if (message.method === method) {
          clearTimeout(timer);
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
    if (!child || this.exitCode !== null) return;
    try {
      await this.request("app.shutdown");
    } catch {
      // 关闭请求失败时直接结束进程。
    }
    await new Promise<void>(resolve => {
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        resolve();
      }, 3000);
      child.on("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    this.child = null;
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
    const bridge = new CoreBridge(
      tempDataDir(),
      process.env.SENTINEL_ACCEPTANCE_MEMORY_SECRETS === "1",
    );
    await bridge.start();
    try {
      await use(bridge);
    } finally {
      await bridge.stop();
    }
  },
  app: async ({ page, core }, use) => {
    let queue: string[] = [];
    await page.exposeFunction("__sentinelSend", (line: string) => {
      core.send(line);
    });
    await page.exposeFunction("__sentinelPoll", () => {
      const lines = queue;
      queue = [];
      return lines;
    });
    await page.addInitScript(installTauriShim);
    const off = core.onLine(line => {
      queue.push(line);
    });
    try {
      await use(page);
    } finally {
      off();
    }
  },
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
