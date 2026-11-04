import { expect, it } from "vitest";
import { formatDate, formatDateTime, formatMoney, formatPercent, formatProbability, formatRelativeTime, formatTime, formatTokens } from "./format";

it.each([
  ["9007199254740993.1250", "$9,007,199,254,740,993.13"], ["99999999999999.9999", "$100,000,000,000,000.00"],
  ["0.0050", "$0.01"], ["-0.0050", "-$0.01"], ["-0.0049", "$0.00"], ["1.234567", "$1.23"],
  ["1234.5600", "$1,234.56"], ["1e8", "—"], ["NaN", "—"], ["", "—"],
])("decimal_money_preserves_precision_and_rounds_half_up: %s", (value, expected) => {
  expect(formatMoney(value)).toBe(expected);
});
it("decimal_money_supports_explicit_price_precision", () => {
  expect(formatMoney("187.250001", "USD", 6)).toBe("$187.250001");
  expect(formatMoney("-1.5", "USD", 0)).toBe("-$2");
  expect(formatMoney("1", "USD", -1)).toBe("—");
});
it("nonfinite_percent_probability_and_unsafe_token_values_are_unknown", () => {
  expect(formatPercent(0.125)).toBe("12.5%");
  expect(formatPercent(0.125, 1, true)).toBe("+12.5%");
  expect(formatProbability(0.9)).toBe("0.90");
  for (const value of [NaN, Infinity, -Infinity]) {
    expect(formatPercent(value)).toBe("—"); expect(formatProbability(value)).toBe("—");
  }
  expect(formatTokens(18420)).toBe("18,420");
  expect(formatTokens(Number.MAX_SAFE_INTEGER + 1)).toBe("—");
});
it("dates_use_explicit_exchange_day_or_utc_instant_and_time_zone", () => {
  expect(formatDate("2026-11-02", "America/New_York")).toBe("11月2日");
  expect(formatDate("2026-11-02T00:35:00Z", "America/New_York")).toBe("11月1日");
  expect(formatTime("2026-11-02T00:35:00Z", "Asia/Shanghai")).toBe("08:35");
  expect(formatDateTime("2026-11-02T00:35:00Z", "UTC")).toContain("00:35");
  for (const value of ["2026-02-30", "2026-11-02T00:35:00", "2026-02-30T00:00:00Z", "nonsense"]) {
    expect(formatDate(value)).toBe("—");
  }
});
it("relative_time_requires_explicit_reference_and_handles_future_values", () => {
  const reference = "2026-11-02T00:35:00Z";
  expect(formatRelativeTime("2026-11-02T00:34:00Z", reference)).toBe("1分钟前");
  expect(formatRelativeTime("2026-11-02T01:35:00Z", reference)).toBe("1小时后");
  expect(formatRelativeTime(reference, reference)).toBe("现在");
  expect(formatRelativeTime(reference, "invalid")).toBe("—");
});
it("utc_microseconds_from_core_to_iso_render_in_every_date_formatter", () => {
  // 已用 sentinel.clock.to_iso(datetime(..., microsecond=123456, tzinfo=UTC)) 核实。
  const value = "2026-11-02T00:35:00.123456Z";
  expect(formatDate(value, "UTC")).toBe("11月2日");
  expect(formatTime(value, "Asia/Shanghai")).toBe("08:35");
  expect(formatDateTime(value, "UTC")).toContain("00:35");
  expect(formatRelativeTime(value, "2026-11-02T00:36:00.123456Z")).toBe("1分钟前");
});
it.each(["9999", "999999", "999999999999"])("utc_fraction_%s_is_truncated_without_rounding_into_next_second_or_day", fraction => {
  const value = `2026-11-02T23:59:59.${fraction}Z`;
  expect(formatTime(value, "UTC")).toBe("23:59");
  expect(formatDate(value, "UTC")).toBe("11月2日");
  expect(formatRelativeTime(value, "2026-11-02T23:59:59.999Z")).toBe("现在");
});
it("utc_submillisecond_precision_is_discarded_in_explicit_reference_comparison", () => {
  expect(formatRelativeTime("2026-11-02T00:35:01.123999Z", "2026-11-02T00:35:00.123001Z")).toBe("1秒钟后");
  expect(formatRelativeTime("2026-11-02T00:35:00.123999Z", "2026-11-02T00:35:00.123001Z")).toBe("现在");
});
it("utc_fractional_parser_still_rejects_invalid_dates_and_wire_syntax", () => {
  for (const value of ["2026-02-30T00:00:00.123456Z", "2026-11-02T24:00:00.123456Z",
    "2026-11-02T00:35:60.123456Z", "2026-11-02T00:35:00.Z", "2026-11-02T00:35:00.123456Z\n",
    "2026-11-02T00:35:00.123456+00:00", "2026-11-02T00:35:00.123456"]) {
    expect(formatDate(value, "UTC")).toBe("—");
    expect(formatTime(value, "UTC")).toBe("—");
    expect(formatRelativeTime(value, "2026-11-02T00:35:00Z")).toBe("—");
  }
});
