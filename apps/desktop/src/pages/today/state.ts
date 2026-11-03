import type { Bootstrap, DecisionSummary, Inbox, ParamsOfNotification, ScanRun } from "../../rpc";

export const VISIBLE_CARDS = 5;
export const PROCESSED_DAYS = 30;
export type TodayState = "no_holdings" | "unconfigured" | "scan_failed" | "offline" | "scanning" | "empty" | "pending";
export function deriveTodayState(inbox: Inbox | null, boot: Bootstrap): TodayState {
  if (inbox?.setup.holdings === 0) return "no_holdings";
  if (!boot.configured.jevKey || !boot.configured.secEmail) return "unconfigured";
  if (inbox?.lastScan?.status === "failed") return "scan_failed";
  if (boot.offline || inbox?.dataStatus.offline) return "offline";
  if (["running", "queued"].includes(inbox?.lastScan?.status ?? "")) return "scanning";
  return inbox?.items.length ? "pending" : "empty";
}
const severity = { overturn: 0, weaken: 1, uncertain: 2, support: 3, none: 4 };
const compareText = (a: string, b: string) => a === b ? 0 : a < b ? -1 : 1;
function compareUtc(a: string, b: string) {
  const [timeA = "", fractionA = ""] = a.slice(0, -1).split("."), [timeB = "", fractionB = ""] = b.slice(0, -1).split(".");
  const digits = Math.max(fractionA.length, fractionB.length);
  return compareText(timeA, timeB) || compareText(fractionA.padEnd(digits, "0"), fractionB.padEnd(digits, "0"));
}
export function sortDecisions(items: DecisionSummary[]) {
  return [...items].sort((a, b) => severity[a.relation] - severity[b.relation] || b.headline - a.headline ||
    compareUtc(b.event.publishedAt, a.event.publishedAt) || compareText(a.decisionId, b.decisionId));
}
export function recount(inbox: Inbox): Inbox {
  return { ...inbox, summary: { pendingCount: inbox.items.length + inbox.uncertain.length,
    overturnCount: inbox.items.filter(d => d.relation === "overturn").length,
    weakenCount: inbox.items.filter(d => d.relation === "weaken").length,
    uncertainCount: inbox.uncertain.length, processedCount: inbox.processed.length } };
}
export function placeDecision(inbox: Inbox, item: DecisionSummary, group?: "items" | "uncertain" | "processed", index = 0): Inbox {
  const next = { ...inbox, items: inbox.items.filter(d => d.decisionId !== item.decisionId),
    uncertain: inbox.uncertain.filter(d => d.decisionId !== item.decisionId), processed: inbox.processed.filter(d => d.decisionId !== item.decisionId) };
  const target = group ?? (item.action && item.action.action !== "reopen" ? "processed" : item.relation === "uncertain" ? "uncertain" : "items");
  next[target].splice(index, 0, item);
  next.items = sortDecisions(next.items);
  next.uncertain = sortDecisions(next.uncertain);
  return recount(next);
}
function object(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function exact(value: Record<string, unknown>, keys: string[]) { return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)); }
function count(value: unknown): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0; }
function text(value: unknown): value is string { return typeof value === "string" && value.trim().length > 0; }
function time(value: unknown) { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value) && Number.isFinite(Date.parse(value)); }
export function validProgress(value: unknown): value is ParamsOfNotification<"scan.progress"> {
  return object(value) && exact(value, ["runId", "market", "stage", "done", "total", "message"]) && text(value.runId) &&
    value.market === "us" && ["fetch", "parse", "decide", "evidence", "finish"].includes(String(value.stage)) &&
    count(value.done) && count(value.total) && value.done <= value.total && typeof value.message === "string";
}
export function validFinished(value: unknown): value is ScanRun {
  if (!object(value) || !exact(value, ["runId", "trigger", "market", "status", "windowStart", "windowEnd", "stats", "engine", "modelId", "startedAt", "finishedAt", "error", "batchSummary"])) return false;
  const stats = value.stats, batches = value.batchSummary, error = value.error;
  return text(value.runId) && value.market === "us" && ["manual", "schedule"].includes(String(value.trigger)) &&
    ["succeeded", "partial", "failed", "cancelled", "interrupted"].includes(String(value.status)) &&
    time(value.windowStart) && time(value.windowEnd) && (value.startedAt === null || time(value.startedAt)) && time(value.finishedAt) &&
    ["jevdb", "jev_direct"].includes(String(value.engine)) && text(value.modelId) &&
    (error === null || object(error) && exact(error, ["code", "message"]) && text(error.code) && text(error.message)) &&
    object(stats) && exact(stats, ["instruments", "skippedNoThesis", "filings", "passages", "decisions", "cachedDecisions", "requests", "inputTokens", "estCostUsd", "durationMs"]) &&
    Object.entries(stats).every(([key, v]) => key === "estCostUsd" ? typeof v === "string" && /^\d+(?:\.\d+)?$/.test(v) : count(v)) &&
    object(batches) && exact(batches, ["total", "succeeded", "failed", "pending"]) && Object.values(batches).every(count);
}
export function validInboxUpdate(value: unknown): value is ParamsOfNotification<"inbox.updated"> {
  return object(value) && exact(value, ["newItems", "pendingCount"]) && count(value.newItems) && count(value.pendingCount);
}
