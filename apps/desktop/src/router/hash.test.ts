import { expect, it } from "vitest";

it("parseHash_reads_route_and_params", async () => {
  const { parseHash } = await import("./hash");
  const state = parseHash("#/today?state=pending&drawer=overturn");
  expect(state.route).toBe("today");
  expect(state.params.get("state")).toBe("pending");
  expect(state.params.get("drawer")).toBe("overturn");
});
it("parseHash_unknown_route_falls_back_to_today", async () => {
  const { parseHash } = await import("./hash");
  expect(parseHash("#/nope").route).toBe("today");
});
it("buildHash_encodes_params_without_question_mark_loss", async () => {
  const { buildHash } = await import("./hash");
  expect(buildHash("today", { state: "scan_failed" })).toBe("#/today?state=scan_failed");
});
