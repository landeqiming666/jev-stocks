import { expect, test, vi } from "vitest";
import { RpcError } from "../rpc/errors";
import { feedback } from "../i18n/zh-CN/feedback";
import { feedbackRootOptions, requestIdOf, toUserMessage } from "./errors";

test("rpc_root_chinese_message_wins_and_data_message_detail_are_never_read", () => {
  const error = new RpcError("CONFLICT", "记录已被其他窗口更新，请刷新。", false,
    { message: "private-message", detail: "test-key-do-not-use", requestId: "r-17-k3j9" });
  expect(toUserMessage(error)).toBe(error.message);
  expect(requestIdOf(error)).toBe("r-17-k3j9");
  expect(toUserMessage({ code: "CONFLICT", data: error.data })).toBe(feedback.errors.CONFLICT);
});

test("all_fifteen_codes_have_a_chinese_fallback", () => {
  expect(Object.keys(feedback.errors)).toHaveLength(15);
  for (const [code, message] of Object.entries(feedback.errors)) expect(toUserMessage({ code })).toBe(message);
});

test("unknown_errors_getters_proxies_and_console_never_expose_error_text", () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const getter = vi.fn(() => { throw new Error("test-key-do-not-use"); });
  for (const error of [new Error("test-key-do-not-use"), "private-thesis", null, { code: "UNKNOWN", message: "private" },
    Object.defineProperty({}, "code", { get: getter }), new Proxy({}, { getOwnPropertyDescriptor: getter })]) {
    expect(toUserMessage(error)).toBe(feedback.unknown);
    expect(requestIdOf(error)).toBeNull();
    feedbackRootOptions.onCaughtError(error);
    feedbackRootOptions.onUncaughtError(error);
    feedbackRootOptions.onRecoverableError(error);
  }
  expect(log).not.toHaveBeenCalled();
  log.mockRestore();
});

test("invalid_request_ids_are_omitted", () => {
  for (const id of ["sk-test-key", "Bearer secret", "x\nprivate", "f".repeat(32), "x".repeat(65), 17])
    expect(requestIdOf({ code: "INTERNAL", data: { requestId: id } })).toBeNull();
});
