import { formatDateTime, formatTokens } from "../../app/format";
import { scan } from "../../i18n/zh-CN/scan";
import type { ScanRun, ScanBatch } from "../../rpc";
import type { Tone } from "../../components/ui/types";

export const missing = "—";
export const number = (value?: number | null) => value == null ? missing : formatTokens(value);
export const time = (value?: string | null) => value ? formatDateTime(value) : missing;
export function cost(value?: string | null) {
  return value && /^\d+\.\d+$/.test(value) ? `$${value}` : missing;
}
export function duration(value?: number | null) {
  if (value == null || !Number.isFinite(value) || value < 0) return missing;
  return value < 1000 ? `${value} ${scan.milliseconds}` : `${Math.round(value / 1000)} ${scan.seconds}`;
}
export function engine(value?: string | null) {
  return value === "jevdb" ? "JEVDB" : value === "jev_direct" ? "Jev 直连" : missing;
}
export const active = (run: ScanRun) => run.market === "us" && ["queued", "running"].includes(run.status);
export const terminal = (run: ScanRun) => !["queued", "running"].includes(run.status);
export const tone: Record<ScanRun["status"] | ScanBatch["status"], Tone> = {
  queued: "info", running: "info", succeeded: "ok", partial: "warn", failed: "danger",
  cancelled: "none", interrupted: "none", pending: "none",
};
