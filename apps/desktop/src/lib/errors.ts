import type { ErrorCode } from "../rpc/generated/types";
import { feedback } from "../i18n/zh-CN/feedback";

// 未知异常可能带 getter 或 Proxy；不调用其 toString、不展开，也不记录原文。
export function ownValue(value: unknown, key: string): unknown {
  try {
    if (typeof value !== "object" || value === null) return undefined;
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && "value" in descriptor ? descriptor.value : undefined;
  } catch { return undefined; }
}
export function errorCodeOf(error: unknown): ErrorCode | null {
  const code = ownValue(error, "code");
  return typeof code === "string" && Object.hasOwn(feedback.errors, code) ? code as ErrorCode : null;
}
export function toUserMessage(error: unknown): string {
  const code = errorCodeOf(error);
  if (!code) return feedback.unknown;
  const message = ownValue(error, "message");
  return typeof message === "string" && message.trim() ? message : feedback.errors[code];
}
export function requestIdOf(error: unknown): string | null {
  if (!errorCodeOf(error)) return null;
  const id = ownValue(ownValue(error, "data"), "requestId");
  return typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(id) &&
    !/^sk-/i.test(id) && !/^[a-f0-9]{32,}$/i.test(id) ? id : null;
}
export function createErrorId(): string {
  return [...crypto.getRandomValues(new Uint8Array(6))].map(n => n.toString(16).padStart(2, "0")).join("").toUpperCase();
}

// React 19 默认根回调会打印原异常；集成 createRoot 时必须传入这组静默回调。
export const feedbackRootOptions = {
  onCaughtError: (error: unknown) => { void error; },
  onUncaughtError: (error: unknown) => { void error; },
  onRecoverableError: (error: unknown) => { void error; },
};
