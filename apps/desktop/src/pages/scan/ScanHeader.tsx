import { Button } from "../../components/ui/Button";
import { scan } from "../../i18n/zh-CN/scan";
import type { ScanRun } from "../../rpc";
import type { ScanControl } from "./useScanRuns";
import { time } from "./format";

export function ScanHeader({ control, disabledReason, lastRun }: {
  control: ScanControl; disabledReason?: string; lastRun?: ScanRun;
}) {
  return <header className="p-page__head">
    <div><h1 className="p-page__title">{scan.title}</h1></div>
    <div className="p-page__actions">
      {lastRun && <span className="u-small u-muted">{["failed", "interrupted"].includes(lastRun.status) ? scan.lastFailed : scan.lastScan} {time(lastRun.startedAt)}</span>}
      {control.activeRunId && <Button loading={control.cancelling} title={control.cancelling ? scan.cancelling : undefined}
        onClick={() => { if (control.activeRunId) void control.cancel(control.activeRunId); }}>{scan.cancel}</Button>}
      <Button variant="primary" icon="play" loading={control.starting}
        disabled={Boolean(disabledReason || control.activeRunId)} disabledReason={disabledReason || scan.runningConflict}
        onClick={() => { void control.start(); }}>{scan.start}</Button>
    </div>
  </header>;
}
