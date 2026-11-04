import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { dismissToast, getToasts, pushToast, subscribeToasts } from "./toast-store";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { getToasts().forEach(item => dismissToast(item.id)); vi.useRealTimers(); });

test("toast_store_keeps_only_three", () => {
  for (const text of ["one", "two", "three", "four"]) pushToast({ tone: "error", text });
  expect(getToasts().map(item => item.text)).toEqual(["two", "three", "four"]);
});

test("toast_store_dedupes_same_text_within_one_second", () => {
  const first = pushToast({ tone: "success", text: "saved" });
  vi.advanceTimersByTime(900);
  expect(pushToast({ tone: "success", text: "saved" })).toBe(first);
  expect(getToasts()).toHaveLength(1);
});

test("dedupe_refreshes_expiry_and_tone_and_window_are_independent", () => {
  const id = pushToast({ tone: "success", text: "saved" });
  vi.advanceTimersByTime(900);
  pushToast({ tone: "success", text: "saved" });
  vi.advanceTimersByTime(3100);
  expect(getToasts().map(item => item.id)).toEqual([id]);
  vi.advanceTimersByTime(900);
  expect(getToasts()).toEqual([]);
  pushToast({ tone: "error", text: "same" });
  pushToast({ tone: "success", text: "same" });
  vi.advanceTimersByTime(1000);
  pushToast({ tone: "error", text: "same" });
  expect(getToasts()).toHaveLength(3);
});

test("listeners_receive_independent_copies_and_cleanup_cancels_evicted_timers", () => {
  const notify = vi.fn();
  const offMutation = subscribeToasts(items => { items[0]!.text = "mutated"; items.pop(); });
  const off = subscribeToasts(notify);
  pushToast({ tone: "success", text: "first" });
  expect(getToasts()[0]!.text).toBe("first");
  expect(notify.mock.calls[0]![0][0].text).toBe("first");
  offMutation(); off();
  for (const text of ["two", "three", "four"]) pushToast({ tone: "error", text });
  expect(vi.getTimerCount()).toBe(0);
  expect(notify).toHaveBeenCalledTimes(1);
});

test("throwing_subscriber_does_not_leak_or_block_other_subscribers", () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {}), notify = vi.fn();
  const offThrow = subscribeToasts(() => { throw new Error("test-key-do-not-use private-thesis"); });
  const off = subscribeToasts(notify);
  expect(() => pushToast({ tone: "error", text: "failed" })).not.toThrow();
  expect(notify).toHaveBeenCalledTimes(1);
  expect(log).not.toHaveBeenCalled();
  offThrow(); off(); log.mockRestore();
});
