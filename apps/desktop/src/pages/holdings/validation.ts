import { holdings as text } from "../../i18n/zh-CN/holdings";
export const STATEMENT_MAX = 500;
export const KILL_MAX = 300;
export const NOTE_MAX = 200;
export const MAX_THESES = 5;

// 与 Python str.strip 和机器契约共用空白集合，避免 UTF-16 长度误判。
export function trimText(value: string): string {
  const whitespace = (c: number) => c >= 9 && c <= 13 || c >= 28 && c <= 32 ||
    [133, 160, 5760, 8232, 8233, 8239, 8287, 12288].includes(c) || c >= 8192 && c <= 8202;
  let start = 0, end = value.length;
  while (start < end && whitespace(value.charCodeAt(start))) start++;
  while (end > start && whitespace(value.charCodeAt(end - 1))) end--;
  return value.slice(start, end);
}
export const countText = (value: string) => Array.from(trimText(value)).length;
export function decimal4(value: string): string | null {
  if (!/^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,4})?(?![\s\S])/.test(value)) return null;
  const [integer, fraction = ""] = value.split(".");
  return `${integer}.${fraction.padEnd(4, "0")}`;
}
export const isWatch = (value: string) => /^0(?:\.0+)?$/.test(value);
export function formatQuantity(value: string): string {
  const [integer = "", fraction = ""] = value.split(".");
  const tail = fraction.replace(/0+$/, "");
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (tail ? "." + tail : "");
}
type Invalid<F> = { ok: false; field: F; code: "EMPTY" | "TOO_LONG" | "INVALID"; message: string };
export function validateThesis(statement: string, killCondition: string):
  Invalid<"statement" | "killCondition"> | { ok: true; statement: string; killCondition: string | null } {
  const s = trimText(statement), k = trimText(killCondition);
  if (!s) return { ok: false, field: "statement", code: "EMPTY", message: text.thesisEmpty };
  if (countText(s) > STATEMENT_MAX) return { ok: false, field: "statement", code: "TOO_LONG", message: text.thesisTooLong };
  if (countText(k) > KILL_MAX) return { ok: false, field: "killCondition", code: "TOO_LONG", message: text.killTooLong };
  return { ok: true, statement: s, killCondition: k || null };
}
export function validateHolding(quantity: string, cost: string, note: string):
  Invalid<"quantity" | "avgCost" | "note"> | { ok: true; quantity: string; avgCost: string | null; note: string | null } {
  const q = decimal4(quantity), c = cost === "" ? null : decimal4(cost), n = trimText(note);
  if (q === null) return { ok: false, field: "quantity", code: "INVALID", message: text.invalidQuantity };
  if (cost !== "" && c === null) return { ok: false, field: "avgCost", code: "INVALID", message: text.invalidCost };
  if (isWatch(q) && c !== null) return { ok: false, field: "avgCost", code: "INVALID", message: text.watchCost };
  if (countText(n) > NOTE_MAX) return { ok: false, field: "note", code: "TOO_LONG", message: text.noteLong };
  return { ok: true, quantity: q, avgCost: c, note: n || null };
}
