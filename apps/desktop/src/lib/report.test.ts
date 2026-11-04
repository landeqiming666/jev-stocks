import { expect, test } from "vitest";
import { RpcError } from "../rpc/errors";
import { buildDiagnostic } from "./report";

test("diagnostic_contains_no_secret_or_thesis", () => {
  const error = new RpcError("INTERNAL", "private-message", true, {
    requestId: "r-17-k3j9", apiKey: "test-key-do-not-use", detail: "private-detail",
    thesis: "private-thesis".repeat(500), holding: "private-holding", cost: "1234.5600",
  });
  const text = buildDiagnostic({ error, appVersion: "0.1.0", protocolVersion: "1.0" });
  expect(text).toContain("INTERNAL");
  expect(text).toContain("r-17-k3j9");
  expect(text).toContain("0.1.0");
  expect(text).toContain("1.0");
  for (const secret of ["private-message", "test-key-do-not-use", "private-detail", "private-thesis", "private-holding", "1234.5600"])
    expect(text).not.toContain(secret);
});

test("diagnostic_has_exact_allowlist_and_unknown_metadata_is_not_stringified", () => {
  const hostile = { message: "test-key-do-not-use", stack: "private-stack", code: "unknown", toString() { throw new Error("private"); } };
  const text = buildDiagnostic({ error: hostile, appVersion: "private-thesis", protocolVersion: "Bearer secret" });
  const result = JSON.parse(text);
  expect(Object.keys(result)).toEqual(["code", "requestId", "appVersion", "protocolVersion", "time"]);
  expect(result).toMatchObject({ code: "INTERNAL", requestId: null, appVersion: "unknown", protocolVersion: "unknown" });
  expect(text.length).toBeLessThanOrEqual(4000);
  expect(result.time).toMatch(/^\d{4}-\d{2}-\d{2}T.*Z$/);
});
