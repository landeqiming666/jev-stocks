import { expect, test } from "vitest";
import { deriveTodayState, sortDecisions, validFinished } from "./state";
import { example, pendingInbox, readyBoot } from "./test-support";
import type { ScanRun } from "../../rpc";

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
