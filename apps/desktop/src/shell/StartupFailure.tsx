import { useEffect, useRef, useState } from "react";
import { common } from "../i18n/zh-CN";
import type { RpcError } from "../rpc";

export function startupMessage(error: RpcError | null) {
  return error?.data.reason === "PROTOCOL_MISMATCH" ? common.protocolMismatch :
    error?.code === "TIMEOUT" ? common.startTimeout : common.startFailed;
}
export function safeErrorDetails(error: RpcError | null) {
  return JSON.stringify({ code: error?.code ?? "INTERNAL", retryable: error?.retryable ?? true,
    message: startupMessage(error), ...(error?.data.reason === "PROTOCOL_MISMATCH" ? { reason: "PROTOCOL_MISMATCH" } : {}) }, null, 2);
}
export function StartupFailure({ error, onRetry }: { error: RpcError | null; onRetry?: () => void }) {
  const [copied, setCopied] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  async function copy() {
    try { await navigator.clipboard.writeText(safeErrorDetails(error)); setCopied(common.copied); }
    catch { setCopied(common.copyFailed); }
  }
  return <section className="l-startup" role="alert">
    <h1 className="u-h1" ref={heading} tabIndex={-1}>{common.startTitle}</h1>
    <p>{startupMessage(error)}</p>
    <div className="u-row">
      <button className="l-action" onClick={onRetry}>{common.retryStart}</button>
      <button className="l-action l-action--secondary" onClick={() => void copy()}>{common.copyErrorDetails}</button>
    </div>
    <p role="status">{copied}</p>
  </section>;
}
