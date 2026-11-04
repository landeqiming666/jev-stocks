import { vi } from "vitest";

export class FakeTransport {
  handlers = new Map<string, (event: { payload: unknown }) => void>();
  lines: Record<string, unknown>[] = [];
  unlisten = vi.fn();
  invoke = vi.fn(async (command: string, args?: { line: string }): Promise<unknown> => {
    if (command === "core_status") return { state: "starting", attempt: 0 };
    if (args) this.lines.push(JSON.parse(args.line) as Record<string, unknown>);
  });
  listen = vi.fn(async (name: string, handler: (event: { payload: unknown }) => void) => {
    this.handlers.set(name, handler);
    return () => { this.handlers.delete(name); this.unlisten(name); };
  });
  emit(name: string, payload: unknown) { this.handlers.get(name)?.({ payload }); }
  ready() { this.emit("core://status", { state: "ready", attempt: 0 }); }
  message(value: unknown) { this.emit("core://message", JSON.stringify(value)); }
  respond(result: unknown, index = 0) {
    this.message({ jsonrpc: "2.0", id: this.lines[index]?.id, result });
  }
}

export async function waitFor() {
  for (let i = 0; i < 12; i++) await Promise.resolve();
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
