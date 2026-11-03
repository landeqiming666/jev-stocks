import type { ErrorCode } from "./generated/types";
import { ERROR_RETRYABLE } from "./generated/methods";

export const RPC_MESSAGES = {
  notReady: "核心进程尚未就绪，请稍后重试。",
  internal: "发生了意外错误，请重试。",
  timeout: "请求超时，请重试。",
  cancelled: "已取消",
  disconnected: "核心进程已断开，请稍后重试。",
  disposed: "连接已关闭，请重新打开。",
  invalid: "请求参数无效，请检查后重试。",
} as const;

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class RpcError extends Error {
  constructor(
    public code: ErrorCode,
    message: string,
    public retryable = ERROR_RETRYABLE[code],
    public data: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "RpcError";
    this.data = { ...data, retryable };
  }

  static fromWire(value: unknown): RpcError {
    if (!isObject(value) || typeof value.code !== "string" || !Object.hasOwn(ERROR_RETRYABLE, value.code)) {
      return new RpcError("INTERNAL", RPC_MESSAGES.internal, false);
    }
    const code = value.code as ErrorCode;
    const data = isObject(value.data) ? value.data : {};
    return new RpcError(code,
      typeof value.message === "string" && value.message.trim() ? value.message : RPC_MESSAGES.internal,
      typeof data.retryable === "boolean" ? data.retryable : ERROR_RETRYABLE[code], data);
  }
}
