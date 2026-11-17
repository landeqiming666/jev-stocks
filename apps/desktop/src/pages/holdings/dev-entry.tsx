// 显式 synthetic fixture：仅 dev-shell.html 使用，生产 RouterView 不导入此文件。
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Application } from "../../app/Application";
import { createRpcClient, type RpcTransport } from "../../rpc/client";
import { RpcError } from "../../rpc";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import type { MethodName } from "../../rpc/generated/methods";
import type { Holding, Thesis } from "../../rpc/generated/types";
import { decimal4, isWatch } from "./validation";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";

const sample = (method: MethodName, name?: string) => {
  const examples = MOCK_EXAMPLES[method] as readonly { name: string; result?: unknown }[];
  return structuredClone((name ? examples.find(e => e.name === name) : examples.find(e => "result" in e))?.result);
};
const holdingResult = sample("holdings.list", "default") as { items: Holding[]; asOf: string };
let holdings = holdingResult.items;
let theses = ["zzar", "zzfd", "zzcl", "zzbk"].flatMap(name => (sample("thesis.list", name) as { items: Thesis[] }).items);
const initialTheses = structuredClone(theses);
const listeners = new Map<string, (event: { payload: unknown }) => void>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const requests: { method: string; params: Record<string, unknown> }[] = [];
let conflict = false, archiveFailure = false, priceMode = "ok", delay = 40, searchDelay = 40;
let searchItems: unknown[] | null = null;
const transport: RpcTransport = {
  async listen(name, handler) { listeners.set(name, handler); return () => { if (listeners.get(name) === handler) listeners.delete(name); }; },
  async invoke(command, args) {
    if (command === "core_status") return { state: "ready", attempt: 0 };
    if (!args) return;
    const request = JSON.parse(args.line) as { id: string; method: MethodName | "$/cancel"; params: Record<string, unknown> };
    if (request.method === "$/cancel") { const id = String(request.params.id); clearTimeout(timers.get(id)); timers.delete(id); return; }
    const { method, params } = request; requests.push({ method, params });
    const timer = setTimeout(() => {
      timers.delete(request.id);
      let result: unknown, error: unknown;
      try {
        if (method === "holdings.list") result = { ...holdingResult, items: holdings };
        else if (method === "thesis.list") result = { items: theses.filter(t => (!params.instrumentId || t.instrumentId === params.instrumentId) && (!params.status || t.status === params.status)) };
        else if (method === "instruments.search") result = { items: searchItems ?? ((sample(method, params.query === "qq" ? "empty" : "ze") as { items: unknown[] }).items) };
        else if (method === "holdings.upsert") {
          const instrument = holdings.find(h => h.instrument.instrumentId === params.instrumentId)?.instrument ??
            (sample("instruments.search", "ze") as { items: Holding["instrument"][] }).items.find(i => i.instrumentId === params.instrumentId)!;
          const quantity = decimal4(String(params.quantity))!;
          result = { ...holdings[0], instrument, quantity, avgCost: params.avgCost, note: params.note,
            marketValue: isWatch(quantity) ? "0.0000" : null, status: "unguarded", thesisCount: 0, pendingCount: 0 };
          holdings = [...holdings.filter(h => h.instrument.instrumentId !== params.instrumentId), result as Holding];
        } else if (method === "holdings.archive") {
          if (archiveFailure) throw new RpcError("INTERNAL", "synthetic archive failure");
          holdings = holdings.filter(h => h.instrument.instrumentId !== params.instrumentId); result = { ok: true };
        } else if (method === "thesis.archive") { theses = theses.filter(t => t.thesisId !== params.thesisId); result = { ok: true }; }
        else if (method === "thesis.update" || method === "thesis.create") {
          const old = theses.find(t => t.thesisId === params.thesisId);
          if (conflict) { conflict = false; if (old) Object.assign(old, { version: old.version + 1, statement: "服务器上的新逻辑" }); throw new RpcError("CONFLICT", "synthetic conflict"); }
          if (old && params.expectedVersion !== old.version) throw new RpcError("CONFLICT", "synthetic conflict");
          result = { ...(old ?? initialTheses[0]), ...params, thesisId: old?.thesisId ?? "synthetic-" + requests.length,
            version: old ? old.version + 1 : 1, versionCount: old ? old.versionCount + 1 : 1, lastDecision: old?.lastDecision ?? null };
          theses = [...theses.filter(t => t !== old), result as Thesis];
        } else if (method === "thesis.versions") result = sample(method);
        else if (method === "prices.refresh") {
          if (priceMode === "offline") throw new RpcError("SOURCE_UNAVAILABLE", "synthetic offline");
          result = { updated: priceMode === "partial" ? 1 : holdings.length, asOf: "2026-10-30", failed: priceMode === "partial" ?
            [{ instrumentId: "us:ZZFD", error: { code: "SOURCE_UNAVAILABLE", message: "synthetic fixture" } },
              { instrumentId: "us:ZZCL", error: { code: "RATE_LIMITED", message: "synthetic fixture" } }] : [] };
        } else result = sample(method);
      } catch (cause) { error = cause instanceof RpcError ? { code: cause.code, message: cause.message, data: { retryable: false } } : { code: "INTERNAL", message: "synthetic", data: { retryable: false } }; }
      listeners.get("core://message")?.({ payload: JSON.stringify({ jsonrpc: "2.0", id: request.id, ...(error ? { error } : { result }) }) });
    }, method === "instruments.search" ? searchDelay : delay);
    timers.set(request.id, timer);
  },
};
Object.assign(window, { u03Fixture: {
  requests, setConflict: () => { conflict = true; }, setArchiveFailure: () => { archiveFailure = true; },
  setPrices: (value: string) => { priceMode = value; }, setDelay: (value: number) => { delay = value; },
  setSearch: (value: unknown[] | null, ms = 40) => { searchItems = value; searchDelay = ms; },
  setLimit: () => { theses = Array.from({ length: 5 }, (_, n) => ({ ...initialTheses[0]!, thesisId: "limit-" + n })); },
  setEmpty: () => { holdings = []; },
} });
const createFixtureClient = () => createRpcClient({ transport });
createRoot(document.getElementById("root")!).render(<StrictMode><Application createClient={createFixtureClient} /></StrictMode>);
