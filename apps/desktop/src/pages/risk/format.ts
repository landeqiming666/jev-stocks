import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";

// 与 QuietLedger 原型的 float 比例格式一致；不接收或转换 Decimal。
export const percent = (value: number) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
export const number = (value: number | null) => value === null || !Number.isFinite(value) ? "—" : value.toFixed(2);
export function cellTitle(a: string, b: string, value: number | null, full = false) {
  return value === null ? risk.nullCell(a, b) : risk.cell(a, b, full ? String(value) : number(value));
}
export function topWeight(result: RiskResult) {
  return result.topWeights.slice(0, 3).reduce((total, item) => total + item.weight, 0);
}
export function unadjusted(result: RiskResult) {
  return result.warnings.some(warning => warning.includes(risk.unadjusted));
}
