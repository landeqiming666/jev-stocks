import { expect, test } from "vitest";
import { validateBudget, validateEmail, validateKey, validateLookback } from "./validation";
import updateContract from "../../../../../contracts/methods/settings.update.json";
import secretContract from "../../../../../contracts/methods/secrets.set.json";

test("settings_budget_rejects_999", () => {
  expect(validateBudget("999")).toMatchObject({ ok: false, error: expect.stringContaining("10000") });
});
test("settings_lookback_rejects_31", () => {
  expect(validateLookback("31")).toMatchObject({ ok: false, error: expect.stringContaining("30") });
});
test.each(["10000", "50000000"])("budget_accepts_real_c04_boundary_%s", value => {
  expect(validateBudget(value)).toEqual({ ok: true, value: Number(value) });
});
test.each(["9999", "50000001", "1e5", "10.5", "", "NaN"])("budget_rejects_%s", value => {
  expect(validateBudget(value).ok).toBe(false);
});
test("email_matches_ascii_dot_atom_c04_policy_and_120_limit", () => {
  const boundary = `${"a".repeat(64)}@${"b".repeat(51)}.com`;
  expect(boundary.length).toBe(120);
  expect(validateEmail(boundary)).toBe(true);
  expect(validateEmail(boundary.replace(".com", "b.com"))).toBe(false);
  for (const value of ["a..b@example.com", "a@-host.com", "a@host.c", "名字@example.com", `${"a".repeat(65)}@example.com`, "a@b.com\nX: y"])
    expect(validateEmail(value)).toBe(false);
  expect(validateEmail(" a+b@example.com ")).toBe(true);
  expect(validateEmail(" ")).toBe(true);
});
test("secret_uses_python_whitespace_and_unicode_codepoints", () => {
  expect(validateKey(" synthetic-only ")).toBe(true);
  expect(validateKey("x\u0085y")).toBe(false);
  expect(validateKey("x\u001cy")).toBe(false);
  expect(validateKey("😀".repeat(512))).toBe(true);
  expect(validateKey("😀".repeat(513))).toBe(false);
});
test("validation_agrees_with_machine_contract_on_real_bounds_and_contact_policy", () => {
  const budget = updateContract.params.properties.dailyTokenBudget;
  expect(validateBudget(String(budget.minimum)).ok).toBe(true);
  expect(validateBudget(String(budget.maximum)).ok).toBe(true);
  expect(validateBudget(String(budget.minimum - 1)).ok).toBe(false);
  expect(validateBudget(String(budget.maximum + 1)).ok).toBe(false);
  const pattern = new RegExp(updateContract.params.properties.secContactEmail.anyOf[0]!.pattern!);
  for (const value of ["", " \u0085", "abc", "a+b@example.com", "\u001ca@b.com\u001c", "a@b.c", "a@b.com\n", "名@b.com", "a..b@c.com", "a@x-.com", "a@b.com\uFEFF"])
    expect(validateEmail(value), JSON.stringify(value)).toBe(pattern.test(value));
});
test("local_secret_validation_agrees_with_machine_contract_without_persisted_fixture", () => {
  const pattern = new RegExp(secretContract.params.properties.value.pattern);
  for (const value of ["", "synthetic-only", " synthetic-only ", "x\u0085y", "\u001cx\u001c", "x\uFEFF", "😀".repeat(512), "😀".repeat(513)])
    expect(validateKey(value)).toBe(pattern.test(value));
});
