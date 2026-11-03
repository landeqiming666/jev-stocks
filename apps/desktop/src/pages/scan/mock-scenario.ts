import type { MockRpcClient, RpcClient } from "../../rpc";
import { SCENARIOS } from "../../mocks/scenarios";

export function selectMockScenario(client: RpcClient | null, state: string) {
  if (import.meta.env.VITE_RPC !== "mock" || !client || !("setExample" in client)) return;
  const examples = SCENARIOS[`scan.${state}`]?.examples;
  const mock = client as MockRpcClient;
  mock.setExample("scan.history", examples?.["scan.history"] ?? "default");
  mock.setExample("scan.detail", "with_failures");
  mock.setExample("scan.start", examples?.["scan.start"] ?? "ok");
}
