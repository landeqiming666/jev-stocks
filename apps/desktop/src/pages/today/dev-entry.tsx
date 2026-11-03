import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Application } from "../../app/Application";
import { createMockRpcClient, RpcError, type Bootstrap, type DecisionSummary, type Inbox, type MockRpcClient, type ParamsOf } from "../../rpc";
import { placeDecision } from "./state";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";

// 开发入口注入已交付的 C-05 mock；交互写回契约数据，生产页面不创建客户端。
function fixtureClient() {
  const client = createMockRpcClient({ scenario: "today.pending", warn: () => {} });
  const original = client.call.bind(client), requests: { method: string; params: unknown }[] = [];
  let cached: Inbox | null = null, failure: string | null = null;
  const demoUnconfigured = () => new URLSearchParams(location.hash.split("?")[1]).get("fixture") === "demo-unconfigured";
  const select = client.setExample.bind(client);
  client.setExample = (method, example) => { if (method === "inbox.list") cached = null; select(method, example); };
  client.call = async (method, params, options) => {
    requests.push({ method, params });
    if (failure === method) { failure = null; throw new RpcError("INTERNAL", "模拟请求失败，请重试。"); }
    const result = await original(method, params, options);
    if (method === "app.bootstrap" && demoUnconfigured()) return { ...(result as Bootstrap), demoDataLoaded: true,
      configured: { jevKey: false, secEmail: false } } as typeof result;
    if (method === "inbox.list") {
      cached ??= result as Inbox;
      if (demoUnconfigured()) cached = { ...cached, uncertain: cached.uncertain.slice(0, 1), summary: { ...cached.summary, pendingCount: cached.items.length + Math.min(1, cached.uncertain.length), uncertainCount: Math.min(1, cached.uncertain.length) } };
      return cached as typeof result;
    }
    if (method === "decision.act" || method === "decision.reopen") {
      const args = params as ParamsOf<"decision.act">;
      const item = cached && [...cached.items, ...cached.uncertain, ...cached.processed].find(d => d.decisionId === args.decisionId);
      if (item && cached) {
        const decision: DecisionSummary = { ...item, action: { action: method === "decision.reopen" ? "reopen" : args.action,
          note: args.note?.trim() || null, actedAt: cached.asOf } };
        cached = placeDecision(cached, decision);
        return decision as typeof result;
      }
    }
    return result;
  };
  window.__u02 = { client, requests, failNext: method => { failure = method; } };
  return client;
}
declare global {
  interface Window { __u02: { client: MockRpcClient; requests: { method: string; params: unknown }[]; failNext: (method: string) => void } }
}
createRoot(document.getElementById("root")!).render(<StrictMode><Application createClient={fixtureClient} /></StrictMode>);
