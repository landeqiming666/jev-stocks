import { settings as text } from "../../i18n/zh-CN/settings";

export const BUDGET_MIN = 10000, BUDGET_MAX = 50000000;
export const LOOKBACK_MIN = 1, LOOKBACK_MAX = 30, EMAIL_MAX = 120, KEY_MAX = 512;
/* C-04 使用 Python 空白集合，必须包含控制字符，不能直接用 JS trim/\s。 */
/* eslint-disable no-control-regex */
const whitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/;
export const normalize = (value: string) => value.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g, "");
/* eslint-enable no-control-regex */
const atom = "[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+";
const label = "[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?";
const emailPattern = new RegExp(`^(?=[\\x21-\\x7E]{1,120}(?![\\s\\S]))(?=[^@]{1,64}@)${atom}(?:\\.${atom})*@${label}(?:\\.${label})*\\.[A-Za-z]{2,63}(?![\\s\\S])`);
export function validateEmail(value: string): boolean {
  const normalized = normalize(value);
  return normalized === "" || emailPattern.test(normalized);
}
export function validateKey(value: string): boolean {
  const normalized = normalize(value), length = Array.from(normalized).length;
  return length > 0 && length <= KEY_MAX && !whitespace.test(normalized);
}
function integer(value: string, min: number, max: number, error: string) {
  const number = Number(value);
  return /^[0-9]+$/.test(value) && Number.isSafeInteger(number) && number >= min && number <= max
    ? { ok: true as const, value: number } : { ok: false as const, error };
}
export const validateBudget = (value: string) => integer(value, BUDGET_MIN, BUDGET_MAX, text.budgetRange);
export const validateLookback = (value: string) => integer(value, LOOKBACK_MIN, LOOKBACK_MAX, text.lookbackRange);
