import { expect, test } from "vitest";
import { deriveTodayState, placeDecision, sortDecisions, validFinished } from "./state";
import { example, pendingInbox, readyBoot } from "./test-support";
import type { DecisionSummary, ScanRun } from "../../rpc";
import sortFixture from "./__fixtures__/p03-sort.json";

test("today_state_priority_and_sort_ties_do_not_mutate_inputs", () => {
  const inbox = pendingInbox(), boot = readyBoot();
  inbox.setup.holdings = 0; boot.configured.jevKey = false; boot.offline = true;
  expect(deriveTodayState(inbox, boot)).toBe("no_holdings");
  inbox.setup.holdings = 1;
  expect(deriveTodayState(inbox, boot)).toBe("unconfigured");
  boot.configured.jevKey = true; inbox.lastScan!.status = "failed";
  expect(deriveTodayState(inbox, boot)).toBe("scan_failed");
  inbox.lastScan!.status = "running";
  expect(deriveTodayState(inbox, boot)).toBe("offline");
  boot.offline = false;
  expect(deriveTodayState(inbox, boot)).toBe("scanning");
  inbox.lastScan!.status = "succeeded";
  expect(deriveTodayState(inbox, boot)).toBe("pending");
  inbox.items = []; inbox.uncertain = [];
  expect(deriveTodayState(inbox, boot)).toBe("empty");
  const items = pendingInbox().items.reverse();
  const sorted = sortDecisions(items);
  expect(sorted.map(item => item.headline)).toEqual([0.93, 0.92, 0.74]);
  expect(items[0]!.relation).toBe("weaken");
});
test("finished_notification_consumes_exact_real_schema_including_six_decimal_cost", () => {
  const run = example<ScanRun>("scan.status", "done");
  expect(validFinished(run)).toBe(true);
  expect(validFinished({ ...run, extra: true })).toBe(false);
  expect(validFinished({ ...run, status: "running" })).toBe(false);
  expect(validFinished({ ...run, stats: { ...run.stats, durationMs: NaN } })).toBe(false);
});
function backendSortItems(): DecisionSummary[] {
  const base = pendingInbox().items[0]!;
  return sortFixture.rows.map(({ publishedAt, ...row }) => ({ ...base, ...row, relation: row.relation as DecisionSummary["relation"],
    event: { ...base.event, publishedAt } }));
}
test("today_same_created_time_sorts_by_backend_publication_then_id", () => {
  const items = backendSortItems(), original = items.map(item => item.decisionId);
  const expected = [items[1]!, items[2]!, items[3]!, items[0]!, items[4]!].map(item => item.decisionId);
  expect(sortDecisions(items).map(item => item.decisionId)).toEqual(expected);
  expect(sortDecisions([...items].reverse()).map(item => item.decisionId)).toEqual(expected);
  expect(items.map(item => item.decisionId)).toEqual(original);
});
test("today_optimistic_reopen_and_rollback_keep_backend_order", () => {
  const items = backendSortItems(), expected = [items[1]!, items[2]!, items[3]!, items[0]!, items[4]!];
  const inbox = { ...pendingInbox(), items: expected };
  const target = items[3]!;
  const moved = placeDecision(inbox, { ...target, action: { action: "ignore", note: null, actedAt: inbox.asOf } });
  const restored = placeDecision(moved, target, "items", 0);
  expect(restored.items.map(item => item.decisionId)).toEqual(expected.map(item => item.decisionId));
  const reopened = placeDecision(moved, { ...target, action: { action: "reopen", note: null, actedAt: inbox.asOf } });
  expect(reopened.items.map(item => item.decisionId)).toEqual(expected.map(item => item.decisionId));
});
