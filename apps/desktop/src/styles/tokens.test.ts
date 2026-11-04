import { expect, it } from "vitest";
import { readFileSync } from "node:fs";

it("tokens_match_contract_values", async () => {
  const { default: raw } = await import("./tokens.css?raw");
  const tokens = raw || readFileSync("src/styles/tokens.css", "utf8");
  expect(tokens).toMatch(/--accent:\s*#C4472D/);
  expect(tokens).toMatch(/--radius-card:\s*10px/);
  expect(tokens).toMatch(/--dur-in:\s*180ms/);
  expect(tokens.match(/:root\s*\{/g)).toHaveLength(1);
});
