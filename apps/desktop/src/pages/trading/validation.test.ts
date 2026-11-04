import { describe, expect, it } from "vitest";
import { formatDecimal, sumMoney, validateAccount, validateOrder } from "./validation";

describe("decimal and input boundaries", () => {
  it("formats large amounts and HALF_UP without Number precision loss", () => {
    expect(formatDecimal("99999999999999.9999", 2, "$" )).toBe("$100,000,000,000,000.00");
    expect(formatDecimal("-0.0050", 2, "$" )).toBe("-$0.01");
    expect(sumMoney(["99999999999999.0001", "0.0001"])).toBe("99999999999999.0002");
    expect(formatDecimal("28.40", 4)).toBe("28.40");
  });
  it.each(["0", "-1", "1.5", "1e2", "1000001", "NaN", "", " 1"])("blocks quantity %s", quantity => {
    expect(validateOrder({ quantity, side: "buy", availableCash: "1.0000", sellable: 0 }).ok).toBe(false);
  });
  it("accepts the maximum integer quantity", () => {
    expect(validateOrder({ quantity: "1000000", side: "buy", availableCash: "1.0000", sellable: 0 }).ok).toBe(true);
  });
  it("trading_insufficient_cash_shows_amounts", () => {
    const result = validateOrder({ quantity: "1", side: "buy", availableCash: "90185.0900", sellable: 0,
      estimate: { amount: "92025.9900", fee: "0.0000" } });
    expect(result.message).toContain("$92,025.99");
    expect(result.message).toContain("$90,185.09");
  });
  it("accounts for pending sells in the provided sellable quantity", () => {
    const result = validateOrder({ quantity: "500", side: "sell", availableCash: "1.0000", sellable: 0 });
    expect(result.code).toBe("INSUFFICIENT_POSITION");
    expect(result.message).toContain("500");
  });
  it.each(["0", "-1", "1e2", "100000000000000", "1.00001", "01", "1."])("blocks initial cash %s", initialCash => {
    expect(validateAccount({ name: "A", initialCash, startDate: "2026-10-29" }).initialCash).toBeTruthy();
  });
  it("accepts 14 integer digits and four decimals; names count codepoints", () => {
    expect(validateAccount({ name: "📝".repeat(30), initialCash: "99999999999999.9999", startDate: "2026-10-29" })).toEqual({});
    expect(validateAccount({ name: "📝".repeat(31), initialCash: "1", startDate: "2026-10-29" }).name).toBeTruthy();
    expect(validateAccount({ name: " ", initialCash: "1", startDate: "2026-02-30" }).startDate).toBeTruthy();
  });
});
