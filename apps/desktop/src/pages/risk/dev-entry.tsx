import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Application } from "../../app/Application";
import { createRpcClient, type RpcTransport, type Bootstrap } from "../../rpc";
import bootstrapWire from "../../app/__fixtures__/bootstrap-unconfigured.json";
import insufficient from "./__fixtures__/insufficient.json";
import { resultFor } from "./__fixtures__/results";
import { risk } from "../../i18n/zh-CN/risk";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";
import "./dev.css";

interface DevCall { method: string; params: Record<string, unknown>; completed: boolean }
interface RiskDev {
  calls: DevCall[]; cancelled: string[]; lateReplies: string[]; state: string;
  failPrices: boolean; failRisk: boolean; delays: Record<string, number>; unmount: () => void;
}
declare global { interface Window { riskDev: RiskDev } }
if (!import.meta.env.DEV) throw new Error("Development fixture only");
const query = new URLSearchParams(location.search);
window.riskDev = {
  calls: [], cancelled: [], lateReplies: [], state: query.get("fixture") ?? "ok",
  failPrices: false, failRisk: false, delays: {}, unmount: () => {},
};
const factory = () => {
  const listeners = new Map<string, (event: { payload: unknown }) => void>();
  const transport: RpcTransport = {
    async listen(name, handler) { listeners.set(name, handler); return () => { listeners.delete(name); }; },
    async invoke(command, args) {
      if (command === "core_status") return { state: "ready", attempt: 0 };
      if (!args) return;
      const request = JSON.parse(args.line) as { id: string; method: string; params: Record<string, unknown> };
      if (request.method === "$/cancel") { window.riskDev.cancelled.push(String(request.params.id)); return; }
      const dev = window.riskDev;
      const call: DevCall = { method: request.method, params: request.params, completed: false };
      dev.calls.push(call);
      let result: unknown, error: unknown;
      if (request.method === "app.bootstrap") {
        result = { ...bootstrapWire, offline: query.get("offline") === "1" } as Bootstrap;
      } else if (request.method === "risk.compute") {
        if (dev.state === "insufficient") error = insufficient;
        else if (dev.failRisk) error = { code: "SOURCE_UNAVAILABLE", message: "虚构行情源不可用", data: { retryable: true } };
        else result = resultFor(dev.state, request.params.window as "6M" | "1Y" | "3Y");
      } else if (request.method === "prices.refresh") {
        if (dev.failPrices) error = { code: "RATE_LIMITED", message: "虚构行情刷新限流", data: { retryable: true } };
        else result = { updated: 5, failed: [], asOf: "2026-10-30" };
      }
      const delay = dev.delays[String(request.params.window ?? request.method)] ?? 0;
      await new Promise<void>(resolve => setTimeout(resolve, delay));
      call.completed = true;
      if (dev.cancelled.includes(request.id)) dev.lateReplies.push(request.id);
      listeners.get("core://message")?.({ payload: JSON.stringify({ jsonrpc: "2.0", id: request.id, ...(error ? { error } : { result }) }) });
    },
  };
  // 故意让取消后的虚构传输迟到，验证真实 RPC client 与页面的旧响应保护。
  return createRpcClient({ transport, warn: () => {} });
};
location.hash ||= "#/risk";
const root = createRoot(document.getElementById("root")!);
window.riskDev.unmount = () => root.unmount();
root.render(<StrictMode><Application createClient={factory} /><aside className="p-risk-dev__mark">{risk.fictional}</aside></StrictMode>);
