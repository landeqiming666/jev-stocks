import { trading as t } from "../../i18n/zh-CN/trading";

function parts(value: string) {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return null;
  return { negative: match[1] === "-", integer: match[2]!, fraction: match[3] ?? "" };
}
export function fixed(value: string, scale: number): bigint {
  const p = parts(value);
  if (!p) throw new Error("Invalid decimal");
  const digits = p.fraction.padEnd(scale, "0");
  let amount = BigInt(p.integer + digits.slice(0, scale));
  if ((digits[scale] ?? "0") >= "5") amount += 1n;
  return p.negative ? -amount : amount;
}
export function fromFixed(value: bigint, scale = 4): string {
  const sign = value < 0n ? "-" : "";
  const digits = (value < 0n ? -value : value).toString().padStart(scale + 1, "0");
  return sign + (scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits);
}
export function sumMoney(values: string[]): string {
  return fromFixed(values.reduce((sum, value) => sum + fixed(value, 4), 0n));
}
export function formatDecimal(value: string | null | undefined, decimals = 2, prefix = ""): string {
  if (value == null) return t.unknown;
  const p = parts(value);
  if (!p) return t.unknown;
  // 原始值没有的小数位不补成虚假的价格精度；金额调用方始终传四位字符串。
  const scale = Math.min(decimals, p.fraction.length);
  const rounded = parts(fromFixed(fixed(value, scale), scale))!;
  return (rounded.negative ? "-" : "") + prefix + rounded.integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (scale ? `.${rounded.fraction}` : "");
}
export const moneyText = (value: string | null | undefined) => formatDecimal(value, 2, "$");
export const integerText = (value: number) => value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
export function dateText(value: string) {
  const date = new Date(value + "T12:00:00Z");
  return `${value}（${t.weekdays[date.getUTCDay()]}）`;
}
export function validateAccount(input: { name: string; initialCash: string; startDate: string }) {
  const errors: { name?: string; initialCash?: string; startDate?: string } = {};
  if (!Array.from(input.name.trim()).length || Array.from(input.name.trim()).length > 30) errors.name = t.invalidName;
  if (!/^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,4})?$/.test(input.initialCash) || fixed(input.initialCash, 4) <= 0n) errors.initialCash = t.invalidCash;
  const date = new Date(input.startDate + "T12:00:00Z");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.startDate) || !Number.isFinite(date.getTime()) ||
    date.toISOString().slice(0, 10) !== input.startDate || input.startDate === "0001-01-01" || input.startDate === "9999-12-31") errors.startDate = t.invalidDate;
  return errors;
}
export function validateOrder(input: { quantity: string; side: "buy" | "sell"; availableCash: string; sellable: number;
  estimate?: { amount: string; fee: string } | null }) {
  if (!/^[1-9][0-9]{0,6}$/.test(input.quantity) || BigInt(input.quantity) > 1000000n)
    return { ok: false, code: "INVALID_QUANTITY", message: t.invalidQuantity };
  if (input.side === "sell" && BigInt(input.quantity) > BigInt(input.sellable))
    return { ok: false, code: "INSUFFICIENT_POSITION", message: t.insufficientPosition(input.sellable, Number(input.quantity)) };
  if (input.side === "buy" && input.estimate) {
    const required = sumMoney([input.estimate.amount, input.estimate.fee]);
    if (fixed(required, 4) > fixed(input.availableCash, 4))
      return { ok: false, code: "INSUFFICIENT_CASH", message: t.insufficientCash(moneyText(required), moneyText(input.availableCash)) };
  }
  return { ok: true };
}
