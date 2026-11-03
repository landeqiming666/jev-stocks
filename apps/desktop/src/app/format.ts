import { common } from "../i18n/zh-CN";

const missing = common.invalidValue;
function validDigits(digits: number) { return Number.isInteger(digits) && digits >= 0 && digits <= 6; }
export function formatMoney(value: string, currency = "USD", digits = 2): string {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match || !validDigits(digits) || !/^[A-Z]{3}$/.test(currency)) return missing;
  const fraction = match[3] ?? "";
  const scale = 10n ** BigInt(digits);
  // Decimal 字符串按 HALF_UP 舍入；只让 Intl 处理整数分组和币种布局。
  let units = BigInt(match[2]!) * scale + BigInt((fraction.slice(0, digits).padEnd(digits, "0")) || "0");
  if (Number(fraction[digits] ?? "0") >= 5) units++;
  const negative = match[1] === "-" && units !== 0n;
  const integer = units / scale;
  const parts = new Intl.NumberFormat("zh-CN", {
    style: "currency", currency, currencyDisplay: "narrowSymbol",
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).formatToParts(negative ? (integer === 0n ? -0 : -integer) : integer);
  return parts.map(part => part.type === "fraction" ? (units % scale).toString().padStart(digits, "0") : part.value).join("");
}
export function formatPercent(value: number, digits = 1, signed = false): string {
  if (!Number.isFinite(value) || !validDigits(digits)) return missing;
  return new Intl.NumberFormat("zh-CN", { style: "percent", minimumFractionDigits: digits,
    maximumFractionDigits: digits, signDisplay: signed ? "exceptZero" : "auto" }).format(value);
}
export function formatProbability(value: number): string {
  return Number.isFinite(value) && value >= 0 && value <= 1 ? value.toFixed(2) : missing;
}
export function formatTokens(value: number): string {
  return Number.isSafeInteger(value) && value >= 0 ? new Intl.NumberFormat("zh-CN").format(value) : missing;
}
function instant(value: string): Date | null {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z(?![\s\S])/.exec(value);
  if (!match) return null;
  // 契约允许微秒及更高精度；截取毫秒，不能舍入越过原始秒或日期。
  const fraction = match[2] ? "." + match[2].slice(0, 3).padEnd(3, "0") : "";
  const date = new Date(match[1] + fraction + "Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === value.slice(0, 19) ? date : null;
}
export function formatDate(value: string, timeZone?: string): string {
  const day = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = instant(day ? value + "T00:00:00Z" : value);
  return date ? new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", timeZone: day ? "UTC" : timeZone }).format(date) : missing;
}
export function formatDateTime(value: string, timeZone?: string): string {
  const date = instant(value);
  return date ? new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit",
    minute: "2-digit", hourCycle: "h23", timeZone }).format(date) : missing;
}
export function formatTime(value: string, timeZone?: string): string {
  const date = instant(value);
  return date ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone }).format(date) : missing;
}
export function formatRelativeTime(value: string, reference: string): string {
  const date = instant(value), now = instant(reference);
  if (!date || !now) return missing;
  const seconds = (date.getTime() - now.getTime()) / 1000;
  const units = [[86400, "day"], [3600, "hour"], [60, "minute"], [1, "second"]] as const;
  const [scale, unit] = units.find(([scale]) => Math.abs(seconds) >= scale) ?? units[3]!;
  return new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" }).format(Math.trunc(seconds / scale), unit);
}
