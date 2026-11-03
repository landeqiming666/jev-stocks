import { describe, expect, it } from "vitest";
import { decimal4, formatQuantity, validateHolding, validateThesis } from "./validation";

describe("portfolio input boundaries", () => {
  it.each(["-5", "NaN", "Infinity", "1e4", "+1", "01", "1.00001", "100000000000000", "1\n"])(
    "rejects decimal outside wire range: %s", value => expect(decimal4(value)).toBeNull(),
  );
  it("keeps the largest Decimal18,4 exact", () => {
    expect(decimal4("99999999999999.9999")).toBe("99999999999999.9999");
    expect(formatQuantity("99999999999999.9999")).toBe("99,999,999,999,999.9999");
    expect(decimal4("0.0001")).toBe("0.0001");
  });
  it("normalizes decimals and optional whitespace", () => {
    expect(validateHolding("1.2", "", " \u0085\u001c ")).toEqual({ ok: true, quantity: "1.2000", avgCost: null, note: null });
  });
  it("watch quantity forbids a nonempty cost as the real service does", () => {
    expect(validateHolding("0", "2", "")).toMatchObject({ ok: false, field: "avgCost" });
  });
  it("trims and counts astral codepoints at 500/300/200", () => {
    expect(validateThesis("  " + "🧪".repeat(500), "🧪".repeat(300))).toMatchObject({ ok: true });
    expect(validateThesis("🧪".repeat(501), "")).toMatchObject({ ok: false, field: "statement", code: "TOO_LONG" });
    expect(validateThesis("valid", "🧪".repeat(301))).toMatchObject({ ok: false, field: "killCondition" });
    expect(validateHolding("1", "", "🧪".repeat(201))).toMatchObject({ ok: false, field: "note" });
    expect(validateHolding("1", "", "🧪".repeat(200))).toMatchObject({ ok: true });
  });
  it("empty thesis and blank kill condition follow Python strip semantics", () => {
    expect(validateThesis(" \u0085\u001c ", "")).toMatchObject({ ok: false, code: "EMPTY" });
    expect(validateThesis(" reason ", " \u0085 ")).toMatchObject({ ok: true, statement: "reason", killCondition: null });
  });
});
