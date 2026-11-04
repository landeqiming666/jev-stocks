import { SCENARIOS } from "../../mocks/scenarios";
import type { ExampleSelection } from "../../mocks/scenarios";
import { createRpcClient } from "../client";
import type { RpcClient, RpcTransport } from "../client";
import { RpcError, RPC_MESSAGES } from "../errors";
import { MOCK_EXAMPLES, MOCK_NOTIFICATIONS } from "../generated/mock-data";
import type { MethodName, NotificationName, ParamsOfNotification } from "../generated/methods";

type Example = { name: string; result?: unknown; error?: unknown };
export interface MockRpcClient extends RpcClient {
  setExample<M extends MethodName>(method: M, example: NonNullable<ExampleSelection[M]>): void;
  setDelay(delayMs: number): void;
  injectNotification<N extends NotificationName>(name: N, params?: ParamsOfNotification<N>): void;
}
export function createMockRpcClient(options: { scenario?: string; delayMs?: number; warn?: (message: string) => void } = {}): MockRpcClient {
  const scenarioName = options.scenario ?? "today.pending";
  const scenario = Object.hasOwn(SCENARIOS, scenarioName) ? SCENARIOS[scenarioName] : undefined;
  if (!scenario) throw new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid);
  const selection: ExampleSelection = { ...scenario.examples };
  const listeners = new Map<string, (event: { payload: unknown }) => void>();
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const warned = new Set<string>();
  let delayMs = options.delayMs ?? 0;
  if (!Number.isFinite(delayMs) || delayMs < 0) throw new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid);
  function emit(value: unknown) { listeners.get("core://message")?.({ payload: JSON.stringify(value) }); }
  const transport: RpcTransport = {
    async listen(name, handler) { listeners.set(name, handler); return () => { listeners.delete(name); }; },
    async invoke(command, args) {
      if (command === "core_status") return { state: "ready", attempt: 0 };
      if (!args) return;
      const request = JSON.parse(args.line) as { id: string; method: MethodName | "$/cancel"; params: { id?: string } };
      if (request.method === "$/cancel") {
        const id = request.params.id ?? ""; clearTimeout(timers.get(id)); timers.delete(id); return;
      }
      const method = request.method;
      const examples: readonly Example[] = MOCK_EXAMPLES[method];
      const name = selection[method];
      if (!name && !warned.has(method)) {
        warned.add(method); (options.warn ?? console.warn)("mock: scenario fallback for " + method);
      }
      const example = name ? examples.find(e => e.name === name) : examples.find(e => Object.hasOwn(e, "result"));
      if (!example) throw new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid);
      const respond = () => {
        timers.delete(request.id);
        emit({ jsonrpc: "2.0", id: request.id, ...("error" in example ? { error: example.error } : { result: example.result }) });
      };
      if (delayMs) timers.set(request.id, setTimeout(respond, delayMs)); else respond();
    },
  };
  const client = createRpcClient({ transport, warn: options.warn });
  return {
    ...client,
    setExample(method, example) { selection[method] = example; },
    setDelay(ms) {
      if (!Number.isFinite(ms) || ms < 0) throw new RpcError("INVALID_ARGUMENT", RPC_MESSAGES.invalid);
      delayMs = ms;
    },
    injectNotification(name, params) {
      emit({ jsonrpc: "2.0", method: name, params: params ?? MOCK_NOTIFICATIONS[name] });
    },
    dispose() { for (const timer of timers.values()) clearTimeout(timer); timers.clear(); client.dispose(); },
  };
}
